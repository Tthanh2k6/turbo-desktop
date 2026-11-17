package dev.turbodesktop.remote

import android.Manifest
import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

/**
 * Placeholder host. The Compose screens are intentionally not built yet: the owner reviews design/mockups first.
 * What IS here and tested: notification Allow/Deny actions (biometric, then signed answer) and, in debug builds only,
 * an adb hook (`dbg_action`) so the hub/app plumbing can be exercised on the emulator without a UI.
 */
class MainActivity : FragmentActivity() {
    private val askNotif = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        androidx.core.view.WindowCompat.setDecorFitsSystemWindows(window, false)
        setContent { App(this) }
        askNotif.launch(Manifest.permission.POST_NOTIFICATIONS)
        handle(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handle(intent)
    }

    private fun handle(i: Intent) {
        val id = i.getStringExtra(Notifier.EXTRA_APPROVAL)
        val decision = i.getStringExtra(Notifier.EXTRA_DECISION)
        if (id != null && decision != null) {
            lifecycleScope.launch {
                if (Biometric.authenticate(this@MainActivity)) Graph.decide(id, decision)
            }
        }
        if (BuildConfig.DEBUG) i.getStringExtra("dbg_action")?.let { debugAction(it, i) }
    }

    private fun debugAction(action: String, i: Intent) = lifecycleScope.launch {
        val log = { m: String -> android.util.Log.i("TurboDbg", m) }
        when (action) {
            "pair" -> if (Biometric.authenticate(this@MainActivity))   // pairing is signed by the biometric-gated key too
                log("pair=" + Graph.pair(i.getStringExtra("text"), i.getStringExtra("url"), i.getStringExtra("code")) + " " + Graph.status.value)
            "set_url" -> Graph.prefs.setUrl(i.getStringExtra("name") ?: "local", i.getStringExtra("url") ?: "")
            "session" -> if (Biometric.authenticate(this@MainActivity))
                log("session=" + Graph.openSession(i.getStringExtra("totp") ?: "") + " " + Graph.status.value)
            "task" -> log("task=" + Graph.sendTask(i.getStringExtra("text") ?: "") + " " + Graph.status.value)
            "stop" -> { Graph.stop(); log("stopped=${Graph.stopped.value}") }
            "onboard" -> Graph.prefs.onboarded = true
            "tab" -> Graph.requestTab.value = i.getStringExtra("name")
            "takeover" -> { Graph.takeOver(); log("paused=${Graph.paused.value}") }
            "resume" -> { Graph.resume(); log("stopped=${Graph.stopped.value}") }
            "state" -> log("state online=${Graph.online.value} via=${Graph.via.value} stopped=${Graph.stopped.value} " +
                "session=${Graph.sessionOpen} left=${Graph.sessionSecondsLeft()} pending=${Graph.pending.value.size} locked=${Graph.inputLocked.value} indicator=${Graph.indicator.value} paused=${Graph.paused.value} " +
                "events=${Graph.events.value.size} last=${Graph.events.value.lastOrNull()?.line(this@MainActivity)} status=${Graph.status.value}")
            "decide" -> if (Biometric.authenticate(this@MainActivity))
                log("decide=" + Graph.decide(i.getStringExtra("id") ?: Graph.pending.value.firstOrNull()?.id ?: "", i.getStringExtra("decision") ?: "deny"))
        }
    }
}
