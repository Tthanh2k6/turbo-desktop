package dev.turbodesktop.remote

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.UUID
import java.util.concurrent.TimeUnit

class Prefs(ctx: Context) {
    private val sp: SharedPreferences = ctx.getSharedPreferences("turbo", Context.MODE_PRIVATE)
    private fun s(k: String) = sp.getString(k, "") ?: ""
    private fun put(k: String, v: String) = sp.edit().putString(k, v).apply()

    var hubKey: String get() = s("hubKey"); set(v) = put("hubKey", v)
    var deviceId: String get() = s("deviceId"); set(v) = put("deviceId", v)
    /** Ways to reach the hub, in the order the hub config lists them (local, lan, tailscale, cloudflare). */
    var urls: List<Pair<String, String>>
        get() = try {
            org.json.JSONArray(s("urls").ifBlank { "[]" }).let { a -> (0 until a.length()).map { a.getJSONObject(it).let { j -> j.getString("name") to j.getString("url") } } }
        } catch (e: Exception) { emptyList() }
        set(v) = put("urls", org.json.JSONArray(v.map { org.json.JSONObject().put("name", it.first).put("url", it.second.trim().trimEnd('/')) }).toString())

    fun setUrl(name: String, url: String) {
        val norm = Protocol.normalizeHttpUrl(url).ifEmpty { url.trim().trimEnd('/') }
        urls = urls.filter { it.first != name } + (name to norm)
    }
    var cfCookie: String get() = s("cfCookie"); set(v) = put("cfCookie", v)
    var activePath: String get() = s("active"); set(v) = put("active", v)
    var sessionId: String get() = s("sessionId"); set(v) = put("sessionId", v)
    var sessionExp: Long get() = sp.getLong("sessionExp", 0); set(v) = sp.edit().putLong("sessionExp", v).apply()
    var relayUrl: String get() = s("relayUrl"); set(v) = put("relayUrl", Protocol.normalizeHttpUrl(v).ifEmpty { v.trim().trimEnd('/') })
    var relayPaired: Boolean get() = sp.getBoolean("relayPaired", false); set(v) = sp.edit().putBoolean("relayPaired", v).apply()
    var preset: String get() = s("preset"); set(v) = put("preset", v)
    var onboarded: Boolean get() = sp.getBoolean("onboarded", false); set(v) = sp.edit().putBoolean("onboarded", v).apply()
    var needsTotp: Boolean get() = sp.getBoolean("needsTotp", true); set(v) = sp.edit().putBoolean("needsTotp", v).apply()
    var needsBiometric: Boolean get() = sp.getBoolean("needsBiometric", true); set(v) = sp.edit().putBoolean("needsBiometric", v).apply()
    var totpEnrollPending: Boolean get() = sp.getBoolean("totpEnrollPending", false); set(v) = sp.edit().putBoolean("totpEnrollPending", v).apply()
    var pcName: String get() = s("pcName"); set(v) = put("pcName", v)
    var screenQuality: String get() = s("screenQuality"); set(v) = put("screenQuality", v)
    var screenFps: Float get() = sp.getFloat("screenFps", 1f); set(v) = sp.edit().putFloat("screenFps", v).apply()
    var showApiCost: Boolean get() = sp.getBoolean("showApiCost", false); set(v) = sp.edit().putBoolean("showApiCost", v).apply()
    var lang: String get() = s("lang"); set(v) = put("lang", v)
    val paired get() = hubKey.isNotBlank() && deviceId.isNotBlank()

    fun unpairLocal() {
        sp.edit().remove("hubKey").remove("deviceId").remove("sessionId").remove("sessionExp").remove("totpEnrollPending").apply()
    }
}

enum class ErrKind { NETWORK, BAD_SIGNATURE, UNSIGNED, ACCESS_LOGIN, REJECTED }

class HubError(val kind: ErrKind, message: String, val status: Int = 0) : Exception(message)

data class Reply(val status: Int, val body: String, val via: String) {
    fun json() = JSONObject(body)
}

data class BytesReply(val status: Int, val bytes: ByteArray, val via: String, val redacted: Int = 0)

/**
 * Signed HTTP client for the hub. Tries each configured transport in order (Tailscale first, Cloudflare second),
 * remembers which one worked, and verifies the hub's signature on every reply so a fake endpoint is detected.
 */
class HubClient(
    private val prefs: Prefs,
    private val plain: Signer,
    private val auth: Signer,
    private val http: OkHttpClient = OkHttpClient.Builder().followRedirects(false)
        .connectTimeout(6, TimeUnit.SECONDS).readTimeout(30, TimeUnit.SECONDS).build(),
    private val nowMs: () -> Long = System::currentTimeMillis,
) {
    @Volatile private var skewMs = 0L

    private fun transports(): List<Pair<String, String>> {
        val all = prefs.urls.filter { it.second.isNotBlank() }
        val first = all.indexOfFirst { it.first == prefs.activePath }
        return if (first > 0) listOf(all[first]) + all.filterIndexed { i, _ -> i != first } else all
    }

    private fun ts() = (nowMs() + skewMs).toString()

    private fun build(
        base: String, label: String, method: String, path: String, body: String?, strong: Boolean,
        session: Boolean, deviceHeader: Boolean = true,
    ): Triple<Request, String, ByteArray> {
        val bytes = body?.toByteArray(Charsets.UTF_8) ?: ByteArray(0)
        val ts = ts()
        val nonce = UUID.randomUUID().toString().replace("-", "")
        val msg = Protocol.canonicalRequest(method, path, bytes, ts, nonce)
        val normalizedBase = Protocol.normalizeHttpUrl(base).ifEmpty { base.trim().trimEnd('/') }
        val rb = try {
            Request.Builder().url(normalizedBase + path)
        } catch (e: IllegalArgumentException) {
            throw IOException("Invalid hub URL: $base", e)
        }
            .header("X-Ts", ts).header("X-Nonce", nonce).header("X-Sig", plain.sign(msg))
        if (deviceHeader) rb.header("X-Device", prefs.deviceId)
        if (strong) rb.header("X-Auth-Sig", auth.sign(msg))
        if (session && prefs.sessionId.isNotBlank()) rb.header("X-Session", prefs.sessionId)
        if (label == "cloudflare" && prefs.cfCookie.isNotBlank()) rb.header("Cookie", "CF_Authorization=${prefs.cfCookie}")
        val req = if (method == "GET") rb.get().build()
        else rb.method(method, bytes.toRequestBody("application/json".toMediaType())).build()
        return Triple(req, nonce, bytes)
    }

    private fun checkReply(status: Int, path: String, body: ByteArray, hubTs: String?, hubSig: String?, nonce: String,
                           location: String?, label: String, pinned: String, replyAtMs: Long = nowMs()): Reply {
        if (status in 300..399 || (location?.contains("cloudflareaccess", true) == true)) {
            throw HubError(ErrKind.ACCESS_LOGIN, "Cloudflare Access needs a login", status)
        }
        if (hubSig == null || hubTs == null) {
            if (status in 200..299) throw HubError(ErrKind.UNSIGNED, "Unsigned reply: not the hub?", status)
            return Reply(status, String(body), label)
        }
        if (pinned.isNotBlank()) {
            if (!Protocol.verify(pinned, Protocol.canonicalResponse(status, path, body, hubTs, nonce), hubSig)) {
                throw HubError(ErrKind.BAD_SIGNATURE, "Hub signature invalid: fake endpoint?", status)
            }
            skewMs = Protocol.computeSkewMs(hubTs, replyAtMs)
        }
        return Reply(status, String(body), label)
    }

    suspend fun call(method: String, path: String, body: JSONObject? = null, strong: Boolean = false,
                     session: Boolean = true): Reply = withContext(Dispatchers.IO) {
        val list = transports()
        if (list.isEmpty()) throw HubError(ErrKind.NETWORK, "No hub URL configured")
        var last: IOException? = null
        for ((label, base) in list) {
            try {
                val (req, nonce, _) = build(base, label, method, path, body?.toString(), strong, session)
                val sentAt = nowMs()
                http.newCall(req).execute().use { r ->
                    val hdrAt = nowMs()
                    val bytes = r.body?.bytes() ?: ByteArray(0)
                    val reply = checkReply(r.code, path, bytes, r.header("X-Hub-Ts"), r.header("X-Hub-Sig"), nonce,
                        r.header("Location"), label, prefs.hubKey, (sentAt + hdrAt) / 2L)
                    prefs.activePath = label
                    return@withContext reply
                }
            } catch (e: IOException) {
                last = e
            }
        }
        throw HubError(ErrKind.NETWORK, "Hub unreachable: ${last?.message}")
    }

    /** Signed binary GET (e.g. /screen.jpg): reuses [build] and [checkReply] to verify the signature over raw bytes. */
    suspend fun callBytes(path: String, session: Boolean = true): BytesReply = withContext(Dispatchers.IO) {
        val list = transports()
        if (list.isEmpty()) throw HubError(ErrKind.NETWORK, "No hub URL configured")
        var last: IOException? = null
        for ((label, base) in list) {
            try {
                val (req, nonce, _) = build(base, label, "GET", path, null, strong = false, session = session)
                val sentAt = nowMs()
                http.newCall(req).execute().use { r ->
                    val bytes = r.body?.bytes() ?: ByteArray(0)
                    checkReply(r.code, path, bytes, r.header("X-Hub-Ts"), r.header("X-Hub-Sig"), nonce,
                        r.header("Location"), label, prefs.hubKey, (sentAt + nowMs()) / 2L)
                    prefs.activePath = label
                    val redacted = r.header("X-Redacted")?.toIntOrNull() ?: 0
                    return@withContext BytesReply(r.code, bytes, label, redacted)
                }
            } catch (e: IOException) {
                last = e
            }
        }
        throw HubError(ErrKind.NETWORK, "Hub unreachable: ${last?.message}")
    }

    /** First contact. Signed by BOTH keys (proof of possession). If [hubKey] is null the hub key is trusted on first use. */
    suspend fun pair(baseUrl: String, hubKey: String?, code: String, deviceName: String,
                     urls: List<Pair<String, String>> = emptyList()): String = withContext(Dispatchers.IO) {
        val normBase = Protocol.normalizeHttpUrl(baseUrl).ifEmpty { baseUrl.trim().trimEnd('/') }
        val body = JSONObject().put("code", code).put("name", deviceName)
            .put("pub", plain.publicKeyB64).put("authPub", auth.publicKeyB64).toString()
        try {
            val (req, nonce, _) = build(normBase, "pair", "POST", "/pair", body, strong = true, session = false, deviceHeader = false)
            val sentAt = nowMs()
            http.newCall(req).execute().use { r ->
                val bytes = r.body?.bytes() ?: ByteArray(0)
                if (r.code != 200) throw HubError(ErrKind.REJECTED, "Pairing refused (${r.code}): ${String(bytes).take(120)}", r.code)
                val midAt = (sentAt + nowMs()) / 2L
                val reply = checkReply(200, "/pair", bytes, r.header("X-Hub-Ts"), r.header("X-Hub-Sig"), nonce,
                    null, "pair", hubKey ?: "", midAt)
                val j = reply.json()
                val got = j.getString("hubPub")
                if (hubKey != null && got != hubKey) throw HubError(ErrKind.BAD_SIGNATURE, "Hub key differs from the QR")
                if (hubKey == null) {
                    if (!Protocol.verify(got, Protocol.canonicalResponse(200, "/pair", bytes,
                            r.header("X-Hub-Ts") ?: "", nonce), r.header("X-Hub-Sig") ?: "")) {
                        throw HubError(ErrKind.BAD_SIGNATURE, "Reply not signed by the key it announces")
                    }
                    skewMs = Protocol.computeSkewMs(r.header("X-Hub-Ts"), midAt)
                }
                prefs.hubKey = got
                prefs.deviceId = j.getString("deviceId")
                HubJson.needs(j).let { prefs.needsTotp = it.totp; prefs.needsBiometric = it.biometric }
                prefs.totpEnrollPending = j.optBoolean("totpEnroll", false)
                prefs.urls = urls.ifEmpty { listOf(Protocol.transportName(normBase) to normBase) }.let { l ->
                    if (l.any { it.second == normBase }) l else listOf(Protocol.transportName(normBase) to normBase) + l }
                got
            }
        } catch (e: IOException) {
            throw HubError(ErrKind.NETWORK, "Cannot reach $normBase: ${e.message}")
        }
    }

    /** Streams signed events (SSE). Blocks until the stream ends; [onEvent] gets each verified event. */
    suspend fun streamEvents(
        since: Long,
        onConnected: (suspend () -> Unit)? = null,
        onDisconnected: (() -> Unit)? = null,
        onEvent: suspend (JSONObject) -> Unit,
    ) = withContext(Dispatchers.IO) {
        // the hub sends a heartbeat every 15 s: 25 s of silence means a half-open connection (airplane mode, Wi-Fi roam, TCP cut)
        val long = http.newBuilder().readTimeout(25_000, TimeUnit.MILLISECONDS).build()
        val path = "/events?since=$since"
        val list = transports()
        var last: IOException? = null
        for ((label, base) in list) {
            var connectedThisAttempt = false
            try {
                val (req, nonce, _) = build(base, label, "GET", path, null, strong = false, session = true)
                val sentAt = nowMs()
                long.newCall(req).execute().use { r ->
                    val hdrAt = nowMs()
                    if (r.code != 200) {
                        val errBody = runCatching { r.body?.string().orEmpty() }.getOrDefault("")
                        throw HubError(if (r.code in 300..399) ErrKind.ACCESS_LOGIN else ErrKind.REJECTED,
                            "events refused (${r.code}): ${errBody.take(120)}", r.code)
                    }
                    checkReply(200, path, ByteArray(0), r.header("X-Hub-Ts"), r.header("X-Hub-Sig"), nonce,
                        null, label, prefs.hubKey, (sentAt + hdrAt) / 2L)
                    prefs.activePath = label
                    connectedThisAttempt = true
                    onConnected?.invoke()
                    val src = r.body!!.source()
                    while (!src.exhausted()) {
                        val line = src.readUtf8Line() ?: break
                        if (!line.startsWith("data:")) continue
                        val frame = JSONObject(line.removePrefix("data:").trim())
                        val payload = frame.getString("p")
                        if (!Protocol.verify(prefs.hubKey, Protocol.canonicalEvent(payload), frame.getString("sig"))) {
                            throw HubError(ErrKind.BAD_SIGNATURE, "Event signature invalid")
                        }
                        onEvent(JSONObject(payload))
                    }
                }
                onDisconnected?.invoke()
                return@withContext
            } catch (e: IOException) {
                if (connectedThisAttempt) onDisconnected?.invoke()
                last = e
            }
        }
        throw HubError(ErrKind.NETWORK, "Hub unreachable: ${last?.message}")
    }
}

/** Calls the Wake-on-LAN relay (stdlib Python on an always-on device). Same signature scheme, its own pairing list. */
class RelayClient(private val prefs: Prefs, private val plain: Signer,
                  private val http: OkHttpClient = OkHttpClient.Builder().connectTimeout(6, TimeUnit.SECONDS)
                      .readTimeout(10, TimeUnit.SECONDS).followRedirects(false).build()) {
    private fun signed(path: String, method: String, body: String): Request {
        val bytes = body.toByteArray()
        val ts = (System.currentTimeMillis() / 1000).toString()
        val nonce = UUID.randomUUID().toString().replace("-", "")
        val sig = plain.sign(Protocol.canonicalRequest(method, path, bytes, ts, nonce))
        val base = Protocol.normalizeHttpUrl(prefs.relayUrl)
        if (base.isEmpty()) throw HubError(ErrKind.NETWORK, "Invalid relay URL")
        return try {
            Request.Builder().url(base + path).header("X-Ts", ts).header("X-Nonce", nonce)
                .header("X-Sig", sig).header("X-Device", Protocol.deviceId(plain.publicKeyB64))
                .method(method, if (method == "GET") null else bytes.toRequestBody("application/json".toMediaType())).build()
        } catch (e: IllegalArgumentException) {
            throw HubError(ErrKind.NETWORK, "Invalid relay URL: ${e.message}")
        }
    }

    suspend fun pair(url: String, code: String, name: String) = withContext(Dispatchers.IO) {
        prefs.relayUrl = url
        val body = JSONObject().put("code", code).put("name", name).put("pub", plain.publicKeyB64).toString()
        http.newCall(signed("/pair", "POST", body)).execute().use {
            if (it.code != 200) throw HubError(ErrKind.REJECTED, "Relay pairing refused (${it.code})", it.code)
            prefs.relayPaired = true
        }
    }

    suspend fun wake(): Boolean = withContext(Dispatchers.IO) {
        http.newCall(signed("/wake", "POST", "")).execute().use { it.code == 200 }
    }
}
