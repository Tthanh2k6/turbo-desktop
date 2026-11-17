package dev.turbodesktop.remote

import android.app.Application
import android.os.Build
import android.util.Base64
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

data class Ev(val seq: Long, val type: String, val json: JSONObject) {
    fun line(c: android.content.Context): String {
        fun opt(k: String) = json.optString(k).takeIf { it != "null" && it.isNotBlank() } ?: ""
        return when (type) {
            "task_started" -> c.getString(R.string.ev_task_started, opt("text"))
            "text" -> opt("text")
            "tool_call" -> c.getString(R.string.ev_tool_call, opt("tool"), opt("control").let { if (it.isEmpty()) "" else "[$it]" })
            "tool_result" -> c.getString(if (json.optBoolean("ok", true)) R.string.ev_tool_ok else R.string.ev_tool_err, opt("summary"))
            "approval_request" -> c.getString(R.string.ev_approval_request, opt("action"), opt("control"), opt("window"))
            "approval_resolved" -> c.getString(R.string.ev_approval_resolved, opt("decision"))
            "final" -> c.getString(R.string.ev_final, opt("text"))
            "task_finished" -> c.getString(R.string.ev_finished, opt("status"))
            "warning" -> c.getString(R.string.ev_warning, opt("text"))
            "hub_alert" -> c.getString(R.string.ev_alert, opt("what"))
            "stopped" -> c.getString(R.string.ev_stopped)
            "indicator" -> c.getString(when (json.optString("state")) { "acting" -> R.string.chip_acting; "input_locked" -> R.string.chip_locked; else -> R.string.chip_idle })
            "input_lock" -> c.getString(if (json.optBoolean("locked")) R.string.ev_input_locked else R.string.ev_input_unlocked)
            "taken_over" -> c.getString(R.string.ev_taken_over)
            "resumed" -> c.getString(R.string.ev_resumed)
            else -> type
        }
    }
}

data class Approval(val id: String, val tool: String, val window: String, val control: String, val action: String,
                    val cropPng: ByteArray?, val expiresAt: Double)

data class Usage(val input: Long = 0, val output: Long = 0, val cacheRead: Long = 0, val cost: Double = 0.0, val tasks: Int = 0) {
    companion object {
        fun from(j: JSONObject?) = if (j == null) Usage() else Usage(j.optLong("input"), j.optLong("output"),
            j.optLong("cache_read"), j.optDouble("cost_usd", 0.0), j.optInt("tasks"))
    }
}

/** Process-wide state, so the foreground service and the UI share one connection. */
object Graph {
    lateinit var app: Application
    lateinit var prefs: Prefs
    lateinit var plain: KeystoreSigner
    lateinit var auth: KeystoreSigner
    lateinit var client: HubClient
    lateinit var relay: RelayClient
    val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    val events = MutableStateFlow<List<Ev>>(emptyList())
    val pending = MutableStateFlow<List<Approval>>(emptyList())
    val tasks = MutableStateFlow<List<JSONObject>>(emptyList())
    val audit = MutableStateFlow<List<JSONObject>>(emptyList())
    val auditOk = MutableStateFlow<Boolean?>(null)
    val stopped = MutableStateFlow(false)
    val inputLocked = MutableStateFlow(false)   // the PC keyboard/mouse is locked while the agent uses real input
    val paused = MutableStateFlow(false)
    val requestTab = MutableStateFlow<String?>(null)   // debug/adb hook: jump to a tab
    val policy = MutableStateFlow<JSONObject?>(null)   // what the hub says is in force (preset, totp, biometric, lock mode...)
    val indicator = MutableStateFlow("idle")    // idle | acting | input_locked: drives the orange frame and the status chip
    val online = MutableStateFlow(false)
    val via = MutableStateFlow("-")
    val status = MutableStateFlow("")            // transient message for the user
    val sessionExp = MutableStateFlow(0L)
    val sessionUsage = MutableStateFlow(Usage())
    val dayUsage = MutableStateFlow(Usage())
    val needAccessLogin = MutableStateFlow(false)
    val wakeState = MutableStateFlow("")
    private var conn: Job? = null
    private var lastSeq = 0L

    fun init(application: Application) {
        if (this::app.isInitialized) return
        app = application
        prefs = Prefs(app)
        plain = KeystoreSigner("turbo_device_key", authRequired = false)
        auth = KeystoreSigner("turbo_auth_key", authRequired = true)
        client = HubClient(prefs, plain, auth)
        relay = RelayClient(prefs, plain)
        sessionExp.value = prefs.sessionExp
        Notifier.createChannels(app)
    }

    val sessionOpen get() = prefs.sessionId.isNotBlank() && prefs.sessionExp > System.currentTimeMillis() / 1000
    fun sessionSecondsLeft(): Long = (prefs.sessionExp - System.currentTimeMillis() / 1000).coerceAtLeast(0)

    fun fail(e: Throwable): String {
        val msg = when {
            e is HubError && e.kind == ErrKind.ACCESS_LOGIN -> { needAccessLogin.value = true; app.getString(R.string.st_access_login) }
            e is HubError -> e.message ?: "Lỗi"
            else -> e.message ?: e.javaClass.simpleName
        }
        status.value = msg
        return msg
    }

    // ---------------------------------------------------------------- pairing
    suspend fun pair(text: String?, urlManual: String?, codeManual: String?): Boolean = try {
        var urls = emptyList<Pair<String, String>>()
        val (url, key, code) = if (!text.isNullOrBlank()) {
            val p = Protocol.parsePairText(text); urls = p.urls; Triple(p.url, p.hubKey, p.code)
        } else Triple(urlManual!!.trim().trimEnd('/'), null, codeManual!!.trim())
        val got = client.pair(url, key, code, app.getString(R.string.device_name_fmt, Build.MANUFACTURER, Build.MODEL), urls)
        status.value = app.getString(R.string.st_paired, Protocol.fingerprint(got))
        true
    } catch (e: Exception) { fail(e); false }

    fun unpairLocal() {
        conn?.cancel(); prefs.unpairLocal(); sessionExp.value = 0; online.value = false; events.value = emptyList()
        HubService.stop(app)
    }

    // ---------------------------------------------------------------- session
    suspend fun openSession(totp: String): Boolean = try {
        val r = client.call("POST", "/session/start", JSONObject().put("totp", totp.trim()), strong = true, session = false)
        if (r.status == 200) {
            val j = r.json()
            prefs.sessionId = j.getString("sessionId"); prefs.sessionExp = j.getLong("expiresAt")
            sessionExp.value = prefs.sessionExp; stopped.value = j.optBoolean("stopped")
            status.value = app.getString(R.string.st_session_open)
            HubService.start(app); startConnection(); true
        } else { status.value = app.getString(R.string.st_session_fail, r.status); false }
    } catch (e: Exception) { fail(e); false }

    // ---------------------------------------------------------------- connection
    fun startConnection() {
        if (conn?.isActive == true) return
        conn = scope.launch(Dispatchers.IO) {
            var backoff = 1000L
            while (isActive && sessionOpen) {
                try {
                    client.streamEvents(lastSeq) { j -> handle(j) }
                    backoff = 1000L
                } catch (e: HubError) {
                    online.value = false
                    if (e.status == 401) { prefs.sessionId = ""; sessionExp.value = 0; status.value = app.getString(R.string.st_session_expired); break }
                    if (e.kind == ErrKind.BAD_SIGNATURE) { status.value = e.message ?: ""; delay(30_000) }
                    fail(e)
                    android.util.Log.w("TurboConn", "hub error: ${e.kind} ${e.message}")
                } catch (e: Exception) { online.value = false; android.util.Log.w("TurboConn", "stream failed: $e") }
                online.value = false
                android.util.Log.i("TurboConn", "reconnect in ${backoff}ms (active=${prefs.activePath}, urls=${prefs.urls})")
                delay(backoff); backoff = (backoff * 2).coerceAtMost(30_000)
            }
            online.value = false
        }
    }

    private suspend fun handle(j: JSONObject) {
        val seq = j.getLong("seq"); lastSeq = maxOf(lastSeq, seq)
        online.value = true; via.value = prefs.activePath
        val ev = Ev(seq, j.getString("type"), j)
        events.update { (it + ev).takeLast(400) }
        when (ev.type) {
            "approval_request" -> {
                val a = Approval(j.getString("approval_id"), j.optString("tool"), j.optString("window"),
                    j.optString("control"), j.optString("action"),
                    j.optString("crop_png_b64").takeIf { it.isNotBlank() && it != "null" }?.let { Base64.decode(it, Base64.DEFAULT) },
                    j.optDouble("expires_at"))
                pending.update { it.filter { x -> x.id != a.id } + a }
                Notifier.showApproval(app, a)
            }
            "approval_resolved" -> { val id = j.getString("approval_id"); pending.update { it.filter { x -> x.id != id } }; Notifier.cancelApproval(app, id) }
            "stopped" -> stopped.value = true
            "resumed" -> { stopped.value = false; paused.value = false }
            "input_lock" -> inputLocked.value = j.optBoolean("locked")
            "indicator" -> indicator.value = j.optString("state", "idle")
            "taken_over" -> { paused.value = true; inputLocked.value = false }
            "task_finished" -> { sessionUsage.value = Usage.from(j.optJSONObject("session_usage")); dayUsage.value = Usage.from(j.optJSONObject("day_usage")); refreshTasks() }
            "hub_alert" -> Notifier.showAlert(app, ev.line(app))
        }
    }

    // ---------------------------------------------------------------- actions
    suspend fun sendTask(text: String): Boolean = try {
        val r = client.call("POST", "/tasks", JSONObject().put("text", text))
        when (r.status) {
            200 -> { status.value = app.getString(R.string.st_task_sent); true }
            423 -> { status.value = r.json().optString("message").ifBlank { app.getString(R.string.st_stopped_hint) }; false }
            409 -> { status.value = app.getString(R.string.st_task_running); false }
            else -> { status.value = app.getString(R.string.st_error_code, r.status); false }
        }
    } catch (e: Exception) { fail(e); false }

    /** Caller must have run BiometricPrompt successfully within the last 30 s. */
    suspend fun decide(id: String, decision: String): Boolean = try {
        val r = client.call("POST", "/approvals/$id", JSONObject().put("decision", decision), strong = true)
        if (r.status == 200) { pending.update { it.filter { x -> x.id != id } }; Notifier.cancelApproval(app, id) }
        else status.value = if (r.status == 409) app.getString(R.string.st_already_decided) else app.getString(R.string.st_error_code, r.status)
        r.status == 200
    } catch (e: Exception) { fail(e); false }

    suspend fun stop() { try { client.call("POST", "/stop", JSONObject()); stopped.value = true } catch (e: Exception) { fail(e) } }
    /** "Lấy lại quyền": releases the PC input lock and pauses the run until [resume]. */
    suspend fun takeOver() { try { client.call("POST", "/takeover", JSONObject()); paused.value = true; inputLocked.value = false } catch (e: Exception) { fail(e) } }
    suspend fun resume() { try { client.call("POST", "/resume", JSONObject()); stopped.value = false } catch (e: Exception) { fail(e) } }

    suspend fun refreshTasks() {
        try {
            val r = client.call("GET", "/tasks"); if (r.status == 200) tasks.value = JSONArray(r.body).let { a -> (0 until a.length()).map { a.getJSONObject(it) } }
            val s = client.call("GET", "/status")
            if (s.status == 200) { policy.value = s.json().optJSONObject("policy"); val u = s.json().optJSONObject("usage"); sessionUsage.value = Usage.from(u?.optJSONObject("session")); dayUsage.value = Usage.from(u?.optJSONObject("today")) }
        } catch (e: Exception) { fail(e) }
    }

    suspend fun refreshAudit() {
        try {
            val r = client.call("GET", "/audit?limit=100")
            if (r.status == 200) { val j = r.json(); auditOk.value = j.getBoolean("chainOk"); val a = j.getJSONArray("entries"); audit.value = (0 until a.length()).map { a.getJSONObject(it) }.reversed() }
        } catch (e: Exception) { fail(e) }
    }

    suspend fun unpairRemote() { try { client.call("POST", "/unpair", JSONObject()) } catch (_: Exception) {}; unpairLocal() }

    // ---------------------------------------------------------------- wake the PC
    suspend fun wakePc() {
        try {
            wakeState.value = app.getString(R.string.wake_sending)
            if (!relay.wake()) { wakeState.value = app.getString(R.string.wake_refused); return }
            wakeState.value = app.getString(R.string.wake_booting)
            val end = System.currentTimeMillis() + 120_000
            while (System.currentTimeMillis() < end) {
                delay(4000)
                val ok = try { client.call("GET", "/hello", session = false).status == 200 } catch (_: Exception) { false }
                if (ok) { wakeState.value = app.getString(R.string.wake_ready); return }
            }
            wakeState.value = app.getString(R.string.wake_timeout)
        } catch (e: Exception) { wakeState.value = app.getString(R.string.wake_relay_fail, e.message ?: "") }
    }
}
