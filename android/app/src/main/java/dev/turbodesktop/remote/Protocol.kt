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

    /** Parses hub timestamp (ms or legacy seconds) and returns clock skew correction in ms beyond small jitter. */
    fun computeSkewMs(hubTs: String?, nowMs: Long): Long {
        val raw = hubTs?.toDoubleOrNull() ?: return 0L
        if (raw.isNaN() || raw.isInfinite()) return 0L
        val isMs = raw >= 1e11
        val hubMs = if (isMs) raw.toLong() else (raw * 1000.0).toLong() + 500L
        val diff = hubMs - nowMs
        val deadzoneMs = if (isMs) 50L else 2_000L
        return if (kotlin.math.abs(diff) > deadzoneMs) diff else 0L
    }

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

    /** Normalises a user-entered hub/relay URL: prefixes http:// when no scheme is present; returns "" if invalid. */
    fun normalizeHttpUrl(raw: String): String {
        val trimmed = raw.trim()
        if (trimmed.isEmpty() || trimmed.any { it.isWhitespace() }) return ""
        val withScheme = when {
            trimmed.startsWith("http://", ignoreCase = true) -> "http://" + trimmed.substring(7)
            trimmed.startsWith("https://", ignoreCase = true) -> "https://" + trimmed.substring(8)
            trimmed.contains("://") -> return ""
            else -> "http://$trimmed"
        }.trimEnd('/')
        val afterScheme = withScheme.substringAfter("://", "")
        if (afterScheme.isBlank() || afterScheme.startsWith("/") || afterScheme.startsWith(":")) return ""
        return withScheme
    }

    /** local | lan | tailscale | cloudflare, guessed from the address when the hub did not name it. */
    fun transportName(url: String): String {
        val norm = normalizeHttpUrl(url).ifEmpty { url.trim() }
        val host = norm.substringAfter("://").substringBefore("/").substringBefore(":")
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

data class ScreenViewConfig(val enabled: Boolean = true, val maxFps: Double = 2.0)

data class ReportDay(
    val date: String,
    val done: Int,
    val failed: Int,
    val stopped: Int,
    val seconds: Long,
) {
    val totalTasks: Int get() = done + failed + stopped
}

data class ReportTotals(
    val done: Int = 0,
    val failed: Int = 0,
    val stopped: Int = 0,
    val seconds: Long = 0L,
    val tokensIn: Long = 0L,
    val tokensOut: Long = 0L,
    val costUsd: Double = 0.0,
) {
    val stoppedOrFailed: Int get() = stopped + failed
    val totalTasks: Int get() = done + failed + stopped
    val totalTokens: Long get() = tokensIn + tokensOut
}

data class ReportApp(val name: String, val count: Int)

data class ReportData(
    val periodDays: Int,
    val days: List<ReportDay>,
    val totals: ReportTotals,
    val topApps: List<ReportApp>,
)

/** Parsers for hub replies, kept pure JVM so they are unit-tested. */
object HubJson {
    /** Missing "needs" (older hub) means "ask for everything": the safe default. */
    fun needs(o: org.json.JSONObject?): Needs {
        val n = o?.optJSONObject("needs") ?: return Needs(totp = true, biometric = true)
        return Needs(n.optBoolean("totp", true), n.optBoolean("biometric", true))
    }

    fun totpEnroll(o: org.json.JSONObject): TotpEnroll =
        TotpEnroll(o.getString("otpauth"), o.getString("secret"), o.optString("issuer", "turbo-desktop"), o.optString("account", "pc"))

    fun screenView(o: org.json.JSONObject?): ScreenViewConfig? {
        val sv = o?.optJSONObject("screenView") ?: o?.optJSONObject("policy")?.optJSONObject("screenView") ?: return null
        val fps = sv.optDouble("maxFps", 2.0).let { if (it.isNaN() || it <= 0.0) 2.0 else it }
        return ScreenViewConfig(enabled = sv.optBoolean("enabled", true), maxFps = fps)
    }

    fun report(periodDays: Int, o: org.json.JSONObject): ReportData {
        val daysArr = o.optJSONArray("days")
        val days = if (daysArr != null) {
            (0 until daysArr.length()).mapNotNull { idx ->
                daysArr.optJSONObject(idx)?.let { d ->
                    ReportDay(
                        date = d.optString("date"),
                        done = d.optInt("done", 0),
                        failed = d.optInt("failed", 0),
                        stopped = d.optInt("stopped", 0),
                        seconds = d.optLong("seconds", 0L),
                    )
                }
            }
        } else emptyList()

        val t = o.optJSONObject("totals")
        val costRaw = t?.optDouble("costUsd", 0.0) ?: 0.0
        val totals = ReportTotals(
            done = t?.optInt("done", 0) ?: 0,
            failed = t?.optInt("failed", 0) ?: 0,
            stopped = t?.optInt("stopped", 0) ?: 0,
            seconds = t?.optLong("seconds", 0L) ?: 0L,
            tokensIn = t?.optLong("tokensIn", 0L) ?: 0L,
            tokensOut = t?.optLong("tokensOut", 0L) ?: 0L,
            costUsd = if (costRaw.isNaN()) 0.0 else costRaw,
        )

        val appsArr = o.optJSONArray("topApps")
        val topApps = if (appsArr != null) {
            (0 until appsArr.length()).mapNotNull { idx ->
                appsArr.optJSONObject(idx)?.let { a ->
                    val name = a.optString("name").trim()
                    if (name.isNotEmpty()) ReportApp(name = name, count = a.optInt("count", 0)) else null
                }
            }
        } else emptyList()

        return ReportData(periodDays = periodDays, days = days, totals = totals, topApps = topApps)
    }

    fun isRealInputVia(via: String): Boolean = via == "input" || via == "ocr"

    /** Resolves the answer to show for a task: live event final answer first, then GET /tasks `answer` field. */
    fun taskAnswer(task: org.json.JSONObject?, eventAnswer: String? = null): String? {
        if (!eventAnswer.isNullOrBlank()) return eventAnswer.trim()
        val raw = task?.optString("answer")?.takeIf { it != "null" && it.isNotBlank() }?.trim()
        return raw
    }

    fun cleanToolName(raw: String): String =
        raw.substringAfterLast("__").replace('_', ' ').trim().ifBlank { raw }

    fun isApprovalAuditKind(kind: String): Boolean =
        kind.startsWith("approval") || kind == "cc_permission_requested" || kind == "cc_permission_resolved"

    fun formatLockMode(mode: String, wholeTaskLabel: String, realInputLabel: String): String = when (mode) {
        "whole_task" -> wholeTaskLabel
        "real_input" -> realInputLabel
        else -> mode
    }

    fun formatCcRequestedTitle(data: org.json.JSONObject, fmt: String): String {
        val control = data.optString("control").takeIf { it != "null" }.orEmpty()
        val tool = data.optString("tool").takeIf { it != "null" }.orEmpty()
        val target = control.ifBlank { cleanToolName(tool) }
        return String.format(fmt, target)
    }

    fun formatCcResolvedTitle(
        data: org.json.JSONObject,
        fmt: String,
        decisionWord: String,
        byPhone: String,
        byPc: String,
        byCc: String,
        fallbackActor: (String) -> String = { it },
    ): String {
        val dec = decisionWord.replaceFirstChar { it.uppercase() }
        val byRaw = data.optString("by").takeIf { it != "null" && it.isNotBlank() }
            ?: data.optString("device").takeIf { it != "null" && it.isNotBlank() }
            ?: ""
        val actor = when (byRaw.lowercase()) {
            "", "phone" -> byPhone
            "pc", "pc-admin", "local-admin" -> byPc
            "claude-code", "claude_code" -> byCc
            else -> fallbackActor(byRaw).ifBlank { byPhone }
        }
        return String.format(fmt, dec, actor)
    }
}
