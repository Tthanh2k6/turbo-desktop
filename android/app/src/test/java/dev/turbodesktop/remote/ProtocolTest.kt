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

    @Test fun hubJsonParsesScreenViewAndReport() {
        val sv = HubJson.screenView(JSONObject("""{"policy":{"screenView":{"enabled":false,"maxFps":1.5}}}"""))!!
        assertFalse(sv.enabled)
        assertEquals(1.5, sv.maxFps, 0.001)

        val rep = HubJson.report(7, JSONObject("""{
            "days":[{"date":"2026-11-16","done":2,"failed":1,"stopped":0,"seconds":120},{"date":"2026-11-17","done":3,"failed":0,"stopped":1,"seconds":412}],
            "totals":{"done":5,"failed":1,"stopped":1,"seconds":532,"tokensIn":32000,"tokensOut":9000,"costUsd":0.145},
            "topApps":[{"name":"Zalo","count":5},{"name":"Calculator","count":2}]
        }"""))
        assertEquals(7, rep.periodDays)
        assertEquals(2, rep.days.size)
        assertEquals(4, rep.days[1].totalTasks)
        assertEquals(5, rep.totals.done)
        assertEquals(2, rep.totals.stoppedOrFailed)
        assertEquals(41000L, rep.totals.totalTokens)
        assertEquals(0.145, rep.totals.costUsd, 0.0001)
        assertEquals("Zalo", rep.topApps[0].name)
        assertEquals(5, rep.topApps[0].count)
    }

    @Test fun canonicalResponseVerifiesOverRawBinaryJpegBytes() {
        val kp = KeyPairGenerator.getInstance("EC").apply { initialize(ECGenParameterSpec("secp256r1")) }.generateKeyPair()
        val pub = Protocol.b64(kp.public.encoded)
        val jpegBytes = byteArrayOf(0xFF.toByte(), 0xD8.toByte(), 0xFF.toByte(), 0xE0.toByte(), 0x00, 0x10, 0x4A, 0x46, 0xFF.toByte(), 0xD9.toByte())
        val canonical = Protocol.canonicalResponse(200, "/screen.jpg?w=960&q=60", jpegBytes, "1800000100", "noncebin")
        val sig = Protocol.b64(Signature.getInstance("SHA256withECDSA").run { initSign(kp.private); update(canonical); sign() })
        assertTrue(Protocol.verify(pub, canonical, sig))
        val tampered = jpegBytes.clone().also { it[5] = 0x11 }
        assertFalse(Protocol.verify(pub, Protocol.canonicalResponse(200, "/screen.jpg?w=960&q=60", tampered, "1800000100", "noncebin"), sig))
    }
}
