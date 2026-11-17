package dev.turbodesktop.remote

import androidx.compose.ui.graphics.asImageBitmap
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

/** Tool results arrive as JSON-in-JSON; show a short readable form. */
fun tidy(s: String): String = s.removePrefix("{\"result\":\"").replace("\\\"", "\"").replace("\\n", " ").replace(Regex("\\s+"), " ").trim().take(110)

/** Localised words for hub codes (decisions, task status) so no English leaks into the Vietnamese UI. */
fun word(c: android.content.Context, code: String): String {
    val id = when (code) {
    "allow" -> R.string.dec_allow; "deny" -> R.string.dec_deny; "timeout" -> R.string.dec_timeout; "stop" -> R.string.dec_stop
    "done" -> R.string.st_done; "failed" -> R.string.st_failed; "stopped" -> R.string.st_stopped; "running" -> R.string.st_running
    else -> return code
    }
    return c.getString(id)
}

data class Ev(val seq: Long, val type: String, val json: JSONObject) {
    /** Structured tool summary ({"k":..,"a":[..]}) rendered from string resources; null when the hub sent only text. */
    fun summaryText(c: android.content.Context): String? {
        val s = json.optJSONObject("sum") ?: return null
        val a = s.optJSONArray("a")
        fun arg(i: Int) = a?.opt(i)?.toString() ?: ""
        return when (s.optString("k")) {
            "opened" -> c.getString(R.string.sum_opened, arg(0), arg(1))
            "acted" -> c.getString(R.string.sum_acted, c.getString(when (arg(0)) {
                "click" -> R.string.verb_click; "invoke" -> R.string.verb_invoke; "type" -> R.string.verb_type; "set_value" -> R.string.verb_set_value
                "select" -> R.string.verb_select; "toggle" -> R.string.verb_toggle; "expand" -> R.string.verb_expand; "focus" -> R.string.verb_focus
                "scroll" -> R.string.verb_scroll; "press_keys" -> R.string.verb_press_keys; else -> R.string.verb_other }), arg(1),
                c.getString(if (arg(2) == "input") R.string.via_input else R.string.via_uia))
            "read_controls" -> c.getString(R.string.sum_read_controls, arg(0).toIntOrNull() ?: 0)
            "read_window" -> c.getString(R.string.sum_read_window)
            "ran_steps" -> c.getString(R.string.sum_ran_steps, arg(0).toIntOrNull() ?: 0, arg(1).toIntOrNull() ?: 0)
            "screenshot" -> c.getString(R.string.sum_screenshot)
            "listed_windows" -> c.getString(R.string.sum_listed_windows, arg(0).toIntOrNull() ?: 0)
            "read_state" -> c.getString(R.string.sum_read_state)
            "waited" -> c.getString(R.string.sum_waited)
            "wait_timeout" -> c.getString(R.string.sum_wait_timeout)
            "failed" -> c.getString(R.string.sum_failed, arg(0))
            else -> arg(0).ifBlank { null }
        }
    }

    fun line(c: android.content.Context): String {
        fun opt(k: String) = json.optString(k).takeIf { it != "null" && it.isNotBlank() } ?: ""
        return when (type) {
            "task_started" -> c.getString(R.string.ev_task_started, opt("text"))
            "text" -> opt("text")
            "tool_call" -> c.getString(R.string.ev_tool_call, opt("tool"), opt("control").let { if (it.isEmpty()) "" else "[$it]" })
            "tool_result" -> c.getString(if (json.optBoolean("ok", true)) R.string.ev_tool_ok else R.string.ev_tool_err, summaryText(c) ?: tidy(opt("summary")))
            "approval_request" -> c.getString(R.string.ev_approval_request, opt("action"), opt("control"), opt("window"))
            "approval_resolved" -> c.getString(R.string.ev_approval_resolved, word(c, opt("decision")))
            "final" -> if (json.optBoolean("ok", true)) c.getString(R.string.ev_final, opt("text")) else c.getString(R.string.ev_tool_err, opt("text"))
            "task_finished" -> c.getString(R.string.ev_finished, word(c, opt("status")))
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
    val taskUsage = MutableStateFlow<Usage?>(null)   // null = the agent reported no usage yet: show a dash, never a fake 0
    val taskRunning = MutableStateFlow(false)   // a task_started without a task_finished yet
    val requestTab = MutableStateFlow<String?>(null)   // debug/adb hook: jump to a tab
    val policy = MutableStateFlow<JSONObject?>(null)   // what the hub says is in force (preset, totp, biometric, lock mode...)
    val indicator = MutableStateFlow("idle")    // idle | acting | input_locked: drives the orange frame and the status chip
    val online = MutableStateFlow(false)
    val via = MutableStateFlow("-")
    val status = MutableStateFlow("")            // transient message for the user
    val sessionExp = MutableStateFlow(0L)
    val sessionId = MutableStateFlow("")      // observable copy of prefs.sessionId so the UI switches screens when it changes
    val sessionUsage = MutableStateFlow(Usage())
    val dayUsage = MutableStateFlow(Usage())
    val needAccessLogin = MutableStateFlow(false)
    val wakeState = MutableStateFlow("")
    /** What the hub asks for before a session opens. Persisted; set at pairing, refreshed by [refreshPolicy]. */
    val needs = MutableStateFlow(Needs(totp = true, biometric = true))
    /** True right after pairing when the hub opened its enrolment window: the UI offers "Add to Authenticator". */
    val totpEnrollPending = MutableStateFlow(false)
    val screenViewEnabled = MutableStateFlow(true)
    val screenViewMaxFps = MutableStateFlow(2.0)
    val lockRemoteTask = MutableStateFlow("")
    val screenFrame = MutableStateFlow<ByteArray?>(null)
    /** Decoded frame for the player. Decoding happens off the main thread (a 960 px JPEG costs ~10-20 ms per frame). */
    val screenBitmap = MutableStateFlow<androidx.compose.ui.graphics.ImageBitmap?>(null)
    /** Owner's chosen refresh rate for the PC screen view; the hub's maxFps still caps it. */
    val screenFps = MutableStateFlow(1.0)
    val screenFrameAtMs = MutableStateFlow(0L)
    val screenRedacted = MutableStateFlow(0)
    val report = MutableStateFlow<ReportData?>(null)
    val reportLoading = MutableStateFlow(false)
    val reportError = MutableStateFlow(false)
    val showApiCost = MutableStateFlow(false)
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
        sessionId.value = prefs.sessionId
        needs.value = Needs(prefs.needsTotp, prefs.needsBiometric)
        totpEnrollPending.value = prefs.totpEnrollPending
        showApiCost.value = prefs.showApiCost
        screenFps.value = prefs.screenFps.toDouble().takeIf { it > 0 } ?: 1.0
        if (prefs.preset == "strict") screenViewEnabled.value = false
        Notifier.createChannels(app)
    }

    fun setScreenFps(fps: Double) {
        prefs.screenFps = fps.toFloat()
        screenFps.value = fps
    }

    fun setShowApiCost(enabled: Boolean) {
        prefs.showApiCost = enabled
        showApiCost.value = enabled
    }

    private fun applyHubMeta(j: JSONObject) {
        j.optString("pcName").takeIf { it.isNotBlank() && it != "null" }?.let { if (it != prefs.pcName) prefs.pcName = it }
        HubJson.screenView(j)?.let { sv ->
            screenViewEnabled.value = sv.enabled
            screenViewMaxFps.value = sv.maxFps
        }
        val lrt = j.optString("lockRemoteTask").takeIf { it.isNotBlank() && it != "null" }
            ?: j.optJSONObject("policy")?.optString("lockRemoteTask")?.takeIf { it.isNotBlank() && it != "null" }
        if (lrt != null) lockRemoteTask.value = lrt
    }

    val sessionOpen get() = prefs.sessionId.isNotBlank() && prefs.sessionExp > System.currentTimeMillis() / 1000
    fun sessionSecondsLeft(): Long = (prefs.sessionExp - System.currentTimeMillis() / 1000).coerceAtLeast(0)

    fun fail(e: Throwable): String {
        val msg = when {
            e is HubError && e.kind == ErrKind.ACCESS_LOGIN -> { needAccessLogin.value = true; app.getString(R.string.st_access_login) }
            e is HubError -> e.message ?: app.getString(R.string.st_error_generic)
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
        needs.value = Needs(prefs.needsTotp, prefs.needsBiometric)
        totpEnrollPending.value = prefs.totpEnrollPending
        status.value = app.getString(R.string.st_paired, Protocol.fingerprint(got))
        true
    } catch (e: Exception) { fail(e); false }

    fun unpairLocal() {
        conn?.cancel()
        prefs.unpairLocal()
        sessionId.value = ""
        sessionExp.value = 0
        online.value = false
        events.value = emptyList()
        screenFrame.value = null
        screenFrameAtMs.value = 0L
        screenRedacted.value = 0
        report.value = null
        taskRunning.value = false
        paused.value = false
        inputLocked.value = false
        indicator.value = "idle"
        HubService.stop(app)
    }

    // ---------------------------------------------------------------- session
    suspend fun openSession(totp: String): Boolean = try {
        val r = client.call("POST", "/session/start", JSONObject().put("totp", totp.trim()), strong = true, session = false)
        if (r.status == 200) {
            val j = r.json()
            prefs.sessionId = j.getString("sessionId"); prefs.sessionExp = j.getLong("expiresAt")
            sessionId.value = prefs.sessionId; sessionExp.value = prefs.sessionExp; stopped.value = j.optBoolean("stopped")
            status.value = app.getString(R.string.st_session_open)
            HubService.start(app); startConnection(); true
        } else {
            // the hub wants a code this app did not know about (e.g. the preset changed on the PC)
            if (r.status == 401 && r.body.contains("totp required") && !needs.value.totp) setNeeds(needs.value.copy(totp = true))
            status.value = app.getString(R.string.st_session_fail, r.status); false
        }
    } catch (e: Exception) { fail(e); false }

    private fun setNeeds(n: Needs) { needs.value = n; prefs.needsTotp = n.totp; prefs.needsBiometric = n.biometric }

    /** Signed GET /policy (no session): learns whether the 2FA code and the fingerprint are required, plus screenView & lock mode. */
    suspend fun refreshPolicy(): Boolean = try {
        val r = client.call("GET", "/policy", session = false)
        if (r.status == 200) {
            val j = r.json()
            online.value = true
            via.value = prefs.activePath
            setNeeds(HubJson.needs(j))
            applyHubMeta(j)
            if (policy.value == null) policy.value = j
            true
        } else false
    } catch (e: Exception) { fail(e); false }

    /**
     * Fetches the Authenticator key. The hub allows it once, only while its enrolment window is open (right after
     * pairing or after `python -m turbo_hub totp`). Caller must have run BiometricPrompt within the last 30 s.
     */
    suspend fun fetchTotpEnrollment(): TotpEnroll? = try {
        val r = client.call("GET", "/totp/enroll", strong = true, session = false)
        if (r.status == 200) {
            totpEnrollPending.value = false; prefs.totpEnrollPending = false
            HubJson.totpEnroll(r.json())
        } else {
            if (r.status == 403) { totpEnrollPending.value = false; prefs.totpEnrollPending = false }
            status.value = if (r.status == 403) app.getString(R.string.st_enroll_closed) else app.getString(R.string.st_error_code, r.status)
            null
        }
    } catch (e: Exception) { fail(e); null }

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
                    if (e.status == 401) { prefs.sessionId = ""; sessionId.value = ""; sessionExp.value = 0; status.value = app.getString(R.string.st_session_expired); break }
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
            "task_started" -> { taskRunning.value = true; paused.value = false; taskUsage.value = null }
            "usage" -> taskUsage.value = Usage.from(j.optJSONObject("usage"))
            // one branch only: Kotlin `when` stops at the first match, a second "task_finished" branch never ran
            "task_finished" -> {
                taskRunning.value = false
                paused.value = false
                inputLocked.value = false
                indicator.value = "idle"
                j.optJSONObject("usage")?.let { u -> Usage.from(u).let { if (it.input + it.output > 0) taskUsage.value = it } }
                j.optJSONObject("session_usage")?.let { sessionUsage.value = Usage.from(it) }
                j.optJSONObject("day_usage")?.let { dayUsage.value = Usage.from(it) }
                val finalSummary = events.value.lastOrNull { it.type == "final" && it.json.optString("task_id") == j.optString("task_id") }
                    ?.json?.optString("text")
                Notifier.showTaskFinished(app, word(app, j.optString("status")), finalSummary)
                scope.launch { refreshTasks() }
            }
            "approval_request" -> {
                val a = Approval(j.getString("approval_id"), j.optString("tool"), j.optString("window"),
                    j.optString("control"), j.optString("action"),
                    j.optString("crop_png_b64").takeIf { it.isNotBlank() && it != "null" }?.let { Base64.decode(it, Base64.DEFAULT) },
                    j.optDouble("expires_at"))
                pending.update { it.filter { x -> x.id != a.id } + a }
                Notifier.showApproval(app, a)
            }
            "approval_resolved" -> { val id = j.getString("approval_id"); pending.update { it.filter { x -> x.id != id } }; Notifier.cancelApproval(app, id) }
            "stopped" -> { stopped.value = true; taskRunning.value = false; paused.value = false; inputLocked.value = false; indicator.value = "idle" }
            "resumed" -> { stopped.value = false; paused.value = false }
            "input_lock" -> inputLocked.value = j.optBoolean("locked")
            "indicator" -> indicator.value = j.optString("state", "idle")
            "taken_over" -> { paused.value = true; inputLocked.value = false; if (indicator.value == "input_locked") indicator.value = "idle" }
            "hub_alert" -> Notifier.showAlert(app, ev.line(app))
        }
    }

    // ---------------------------------------------------------------- actions
    suspend fun sendTask(text: String): Boolean = try {
        val r = client.call("POST", "/tasks", JSONObject().put("text", text))
        when (r.status) {
            200 -> { status.value = app.getString(R.string.st_task_sent); true }
            423 -> { status.value = r.json().optString("message").ifBlank { app.getString(R.string.st_stopped_hint) }; false }
            409 -> { status.value = app.getString(R.string.st_task_running); taskRunning.value = true; false }
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

    suspend fun stop() { try { client.call("POST", "/stop", JSONObject()); stopped.value = true; taskRunning.value = false; paused.value = false; inputLocked.value = false; indicator.value = "idle" } catch (e: Exception) { fail(e) } }
    /** "Lấy lại quyền": releases the PC input lock and pauses the run until [resume]. */
    suspend fun takeOver() { try { client.call("POST", "/takeover", JSONObject()); paused.value = true; inputLocked.value = false; if (indicator.value == "input_locked") indicator.value = "idle" } catch (e: Exception) { fail(e) } }
    suspend fun resume() { try { client.call("POST", "/resume", JSONObject()); stopped.value = false; paused.value = false } catch (e: Exception) { fail(e) } }

    suspend fun refreshTasks() {
        try {
            val r = client.call("GET", "/tasks")
            if (r.status == 200) {
                online.value = true
                via.value = prefs.activePath
                tasks.value = JSONArray(r.body).let { a -> (0 until a.length()).map { a.getJSONObject(it) } }
            }
            val s = client.call("GET", "/status")
            if (s.status == 200) {
                val sj = s.json()
                online.value = true
                via.value = prefs.activePath
                stopped.value = sj.optBoolean("stopped", stopped.value)
                paused.value = sj.optBoolean("paused", paused.value)
                val runningId = sj.optString("running").takeIf { it.isNotBlank() && it != "null" }
                taskRunning.value = runningId != null
                sj.optJSONObject("inputLock")?.let { inputLocked.value = it.optBoolean("locked", false) }
                sj.optString("indicator").takeIf { it.isNotBlank() && it != "null" }?.let { indicator.value = it }
                sj.optJSONObject("policy")?.let { policy.value = it }
                applyHubMeta(sj)
                val u = sj.optJSONObject("usage")
                sessionUsage.value = Usage.from(u?.optJSONObject("session"))
                dayUsage.value = Usage.from(u?.optJSONObject("today"))
            }
        } catch (e: Exception) { fail(e) }
    }

    suspend fun fetchScreenFrame(): Int = try {
        val r = client.callBytes("/screen.jpg?w=960&q=60")
        when (r.status) {
            200 -> {
                online.value = true
                via.value = prefs.activePath
                if (r.bytes.isNotEmpty()) {
                    val bmp = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Default) {
                        android.graphics.BitmapFactory.decodeByteArray(r.bytes, 0, r.bytes.size)
                    }
                    if (bmp != null) screenBitmap.value = bmp.asImageBitmap()
                    screenFrame.value = r.bytes
                    screenFrameAtMs.value = System.currentTimeMillis()
                    screenRedacted.value = r.redacted
                }
            }
            403 -> screenViewEnabled.value = false
            401 -> {
                prefs.sessionId = ""
                sessionId.value = ""
                sessionExp.value = 0
                status.value = app.getString(R.string.st_session_expired)
            }
            429 -> Unit
        }
        r.status
    } catch (e: HubError) {
        when (e.kind) {
            ErrKind.ACCESS_LOGIN -> {
                needAccessLogin.value = true
                status.value = app.getString(R.string.st_access_login)
                302
            }
            ErrKind.BAD_SIGNATURE, ErrKind.UNSIGNED -> {
                fail(e)
                -1
            }
            else -> 0
        }
    } catch (_: Exception) {
        0
    }

    suspend fun refreshReport(days: Int) {
        val validDays = if (days in setOf(1, 7, 30)) days else 7
        reportLoading.value = true
        reportError.value = false
        try {
            val r = client.call("GET", "/report?days=$validDays")
            if (r.status == 200) {
                online.value = true
                via.value = prefs.activePath
                report.value = HubJson.report(validDays, r.json())
            } else {
                reportError.value = true
            }
        } catch (e: Exception) {
            if (e is HubError && e.kind == ErrKind.ACCESS_LOGIN) needAccessLogin.value = true
            reportError.value = true
        } finally {
            reportLoading.value = false
        }
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
