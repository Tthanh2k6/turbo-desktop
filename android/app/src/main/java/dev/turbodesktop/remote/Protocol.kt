package dev.turbodesktop.remote

import java.security.KeyFactory
import java.security.MessageDigest
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.util.Base64

/** Wire format shared with hub/turbo_hub/crypto.py. Pure JVM so it is unit-tested without a device. */
object Protocol {
    const val MAX_SKEW_SECONDS = 60

    fun sha256Hex(data: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(data).joinToString("") { "%02x".format(it) }

    fun canonicalRequest(method: String, pathQs: String, body: ByteArray, ts: String, nonce: String): ByteArray =
        "${method.uppercase()}\n$pathQs\n${sha256Hex(body)}\n$ts\n$nonce".toByteArray(Charsets.UTF_8)

    fun canonicalResponse(status: Int, pathQs: String, body: ByteArray, ts: String, nonce: String): ByteArray =
        "RESP\n$status\n$pathQs\n${sha256Hex(body)}\n$ts\n$nonce".toByteArray(Charsets.UTF_8)

    fun canonicalEvent(payload: String): ByteArray = "EVT\n$payload".toByteArray(Charsets.UTF_8)

    fun b64(data: ByteArray): String = Base64.getEncoder().encodeToString(data)
    fun unb64(s: String): ByteArray = Base64.getDecoder().decode(s)

    fun deviceId(pubB64: String): String = sha256Hex(unb64(pubB64)).take(16)

    fun fingerprint(pubB64: String): String =
        sha256Hex(unb64(pubB64)).take(20).uppercase().chunked(4).joinToString(" ")

    /** ECDSA P-256 / SHA-256 verify of a DER signature against an X.509 SPKI public key. */
    fun verify(pubB64: String, message: ByteArray, sigB64: String): Boolean = try {
        val pub = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(unb64(pubB64)))
        Signature.getInstance("SHA256withECDSA").run {
            initVerify(pub)
            update(message)
            verify(unb64(sigB64))
        }
    } catch (e: Exception) {
        false
    }

    /** What the QR / pasted pairing text contains. */
    data class PairPayload(val url: String, val hubKey: String?, val code: String, val exp: Long,
                           val urls: List<Pair<String, String>> = emptyList())

    fun parsePairText(text: String): PairPayload {
        val t = text.trim()
        val json = if (t.startsWith("turbo-pair:")) {
            String(Base64.getUrlDecoder().decode(t.removePrefix("turbo-pair:")), Charsets.UTF_8)
        } else t
        val o = org.json.JSONObject(json)
        val list = o.optJSONArray("urls")?.let { a ->
            (0 until a.length()).map { a.getJSONObject(it).let { j -> j.getString("name") to j.getString("url").trimEnd('/') } }
        } ?: emptyList()
        return PairPayload(o.getString("url").trimEnd('/'), o.optString("hubKey").ifBlank { null },
            o.getString("code"), o.optLong("exp", 0), list)
    }

    /** local | lan | tailscale | cloudflare, guessed from the address when the hub did not name it. */
    fun transportName(url: String): String {
        val host = url.substringAfter("://").substringBefore("/").substringBefore(":")
        val o = host.split(".").mapNotNull { it.toIntOrNull() }
        return when {
            host == "localhost" || host == "127.0.0.1" || host == "10.0.2.2" -> "local"
            o.size == 4 && o[0] == 100 && o[1] in 64..127 -> "tailscale"
            o.size == 4 && (o[0] == 10 || o[0] == 192 && o[1] == 168 || o[0] == 172 && o[1] in 16..31) -> "lan"
            else -> "cloudflare"
        }
    }
}

/** Signs canonical bytes. Android implementation lives in Keys.kt; tests use a software key. */
interface Signer {
    val publicKeyB64: String
    fun sign(message: ByteArray): String
}

/** What the hub requires before a session opens; the app hides the 2FA field when [totp] is false. */
data class Needs(val totp: Boolean, val biometric: Boolean)

/** The Authenticator key as the hub sends it from GET /totp/enroll. [secret] is base32 without padding. */
data class TotpEnroll(val otpauth: String, val secret: String, val issuer: String, val account: String)

/** Parsers for hub replies, kept pure JVM so they are unit-tested. */
object HubJson {
    /** Missing "needs" (older hub) means "ask for everything": the safe default. */
    fun needs(o: org.json.JSONObject?): Needs {
        val n = o?.optJSONObject("needs") ?: return Needs(totp = true, biometric = true)
        return Needs(n.optBoolean("totp", true), n.optBoolean("biometric", true))
    }

    fun totpEnroll(o: org.json.JSONObject): TotpEnroll =
        TotpEnroll(o.getString("otpauth"), o.getString("secret"), o.optString("issuer", "turbo-desktop"), o.optString("account", "pc"))
}
