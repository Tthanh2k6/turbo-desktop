package dev.turbodesktop.remote

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.security.KeyPairGenerator
import java.security.Signature
import java.security.spec.ECGenParameterSpec

class ProtocolTest {
    private val v = JSONObject(javaClass.getResource("/vectors.json")!!.readText())

    @Test fun canonicalRequestMatchesHubByteForByte() {
        val r = v.getJSONObject("request")
        val c = Protocol.canonicalRequest(r.getString("method"), r.getString("path"), r.getString("body").toByteArray(),
            r.getString("ts"), r.getString("nonce"))
        assertEquals(r.getString("canonical"), String(c, Charsets.UTF_8))
        assertEquals(r.getString("bodySha256"), Protocol.sha256Hex(r.getString("body").toByteArray()))
    }

    @Test fun verifiesSignatureMadeByHubCode() {
        val r = v.getJSONObject("request")
        val msg = r.getString("canonical").toByteArray()
        assertTrue(Protocol.verify(v.getString("pub"), msg, r.getString("sig")))
        assertFalse(Protocol.verify(v.getString("pub"), msg + "x".toByteArray(), r.getString("sig")))
        assertFalse(Protocol.verify(v.getString("pub"), msg, "AAAA"))
    }

    @Test fun responseAndEventFramesMatchHub() {
        val r = v.getJSONObject("response")
        val c = Protocol.canonicalResponse(r.getInt("status"), r.getString("path"), r.getString("body").toByteArray(),
            r.getString("ts"), r.getString("nonce"))
        assertEquals(r.getString("canonical"), String(c))
        assertTrue(Protocol.verify(v.getString("pub"), c, r.getString("sig")))
        val e = v.getJSONObject("event")
        val ec = Protocol.canonicalEvent(e.getString("payload"))
        assertEquals(e.getString("canonical"), String(ec))
        assertTrue(Protocol.verify(v.getString("pub"), ec, e.getString("sig")))
    }

    @Test fun deviceIdAndFingerprintMatchHub() {
        assertEquals(v.getString("deviceId"), Protocol.deviceId(v.getString("pub")))
        assertEquals(v.getString("fingerprint"), Protocol.fingerprint(v.getString("pub")))
    }

    @Test fun androidStyleSignatureRoundTripsAndIsExportedForHubTest() {
        val kp = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
        val pub = Protocol.b64(kp.public.encoded)
        val msg = Protocol.canonicalRequest("GET", "/status", ByteArray(0), "1800000000", "n1")
        val sig = Protocol.b64(Signature.getInstance("SHA256withECDSA").run { initSign(kp.private); update(msg); sign() })
        assertTrue(Protocol.verify(pub, msg, sig))
        // the hub's test suite reads this file and verifies it with python-cryptography
        val out = File("build/test-vectors").apply { mkdirs() }
        File(out, "kotlin_vector.json").writeText(JSONObject().put("pub", pub).put("canonical", String(msg)).put("sig", sig).toString())
    }

    @Test fun pairingTextParsing() {
        val json = """{"v":1,"url":"http://10.0.2.2:8750/","hubKey":"KEY","code":"123456","exp":1800000300}"""
        val enc = "turbo-pair:" + java.util.Base64.getUrlEncoder().encodeToString(json.toByteArray())
        val p = Protocol.parsePairText(enc)
        assertEquals("http://10.0.2.2:8750", p.url)
        assertEquals("123456", p.code)
        assertEquals("KEY", p.hubKey)
        assertEquals("123456", Protocol.parsePairText(json).code)       // raw JSON also accepted
    }

    @Test fun totpMatchesRfc6238Vectors() {
        val secret = "12345678901234567890".toByteArray()
        assertEquals("287082", Totp.code(secret, 59 / 30))
        assertEquals("081804", Totp.code(secret, 1111111109L / 30))
        assertEquals("005924", Totp.code(secret, 1234567890L / 30))
        assertTrue(Totp.looksValid("012345"))
        assertFalse(Totp.looksValid("12345")); assertFalse(Totp.looksValid("12a456"))
    }
}
