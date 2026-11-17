package dev.turbodesktop.remote

import androidx.activity.compose.setContent
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.getUnclippedBoundsInRoot
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.isToggleable
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithTag
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.unit.dp
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.json.JSONObject
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Compose UI tests on the Android 16 emulator. They render single screens with fake Graph state; no hub is needed. */
@RunWith(AndroidJUnit4::class)
class UiTest {
    // the notification-permission dialog would otherwise take window focus and hide the Compose hierarchy
    @get:Rule(order = 0) val perm: androidx.test.rule.GrantPermissionRule =
        androidx.test.rule.GrantPermissionRule.grant(android.Manifest.permission.POST_NOTIFICATIONS, android.Manifest.permission.CAMERA)
    @get:Rule(order = 1) val rule = createAndroidComposeRule<MainActivity>()

    private fun str(id: Int) = rule.activity.getString(id)

    private fun show(content: @androidx.compose.runtime.Composable () -> Unit) {
        rule.activity.runOnUiThread { rule.activity.setContent { TurboTheme { content() } } }
        rule.waitForIdle()
    }

    @Test fun welcomeOffersThreePresetsAndEasyMentionsWifi() {
        show { Welcome { } }
        rule.onNodeWithTag("preset0").assertIsDisplayed()
        rule.onNodeWithTag("preset1").assertIsDisplayed()
        rule.onNodeWithTag("preset2").assertIsDisplayed()
        rule.onNodeWithTag("preset0").assertTextContains("Wi-Fi", substring = true)
        rule.onNodeWithTag("preset2").performClick()
        rule.onNodeWithTag("usePreset").assertTextContains(str(R.string.preset_strict), substring = true, ignoreCase = true)
    }

    @Test fun settingsTextNeverRunsUnderTheToggle() {
        Graph.policy.value = JSONObject("""{"preset":"balanced","totp":true,"biometric":false,"lockMode":"real_input","cfAccess":false,"ask":["send"]}""")
        show { SettingsTab(rule.activity) { } }
        rule.onNodeWithTag("level").assertTextContains(str(R.string.preset_balanced), substring = true)
        // the 'floor' row has the longest description; its text column must end before the switch begins
        val row = rule.onNodeWithTag("row_floor").getUnclippedBoundsInRoot()
        val toggleWidth = 52.dp   // a Material3 Switch
        val desc = rule.onNodeWithText(str(R.string.set_row_floor_d), useUnmergedTree = true).getUnclippedBoundsInRoot()
        assertTrue("description ends at ${desc.right} but the toggle starts at ${row.right - 16.dp - toggleWidth}", desc.right <= row.right - 16.dp - toggleWidth)
        assertTrue((row.right - row.left) > 200.dp)
        rule.onNodeWithText(str(R.string.set_lock_real), substring = true).assertIsDisplayed()
        rule.onNodeWithTag("row_border").assertIsDisplayed()
    }

    @Test fun approvalShowsWhatTheAiWantsAndThenButtons() {
        val png = android.util.Base64.decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", 0)
        Graph.pending.value = listOf(Approval("a1", "mcp", "Mail", "Send", "click", png, System.currentTimeMillis() / 1000.0 + 100))
        show { ApprovalsTab(rule.activity) }
        rule.onNodeWithTag("approval").assertIsDisplayed()
        rule.onNodeWithText("Send", substring = true).assertIsDisplayed()
        rule.onNodeWithTag("deny").assertIsDisplayed()
        rule.onNodeWithTag("allow").assertIsDisplayed()
        Graph.pending.value = emptyList()
    }

    @Test fun liveShowsTakeOverWhileLocked() {
        // v3: the status lives in the top bar and the locked line in the task card; the Việc screen alone must
        // still offer "Lấy lại quyền" whenever the PC input is locked, and hide it when idle.
        Graph.indicator.value = "input_locked"; Graph.inputLocked.value = true; Graph.paused.value = false
        show { LiveTab() }
        rule.onNodeWithTag("takeover").assertIsDisplayed()
        Graph.indicator.value = "idle"; Graph.inputLocked.value = false; Graph.taskRunning.value = false
        rule.waitForIdle()
        rule.onNodeWithTag("takeover").assertDoesNotExist()
    }

    @Test fun stopCardOffersResume() {
        show { StopCard() }
        rule.onNodeWithTag("stopCard").assertIsDisplayed()
        rule.onNodeWithTag("resume").assertIsDisplayed()
    }

    @Test fun auditShowsBrokenChainWarning() {
        Graph.auditOk.value = false
        Graph.audit.value = listOf(JSONObject("""{"ts":1800000000.0,"kind":"stop","data":{"device":"x"}}"""))
        show { AuditTab() }
        rule.onNodeWithText(str(R.string.audit_bad)).assertIsDisplayed()
    }

    @Test fun approvalClaudeCodeShowsChipDetailAndNoCountdown() {
        Graph.pending.value = listOf(
            Approval(
                id = "c1",
                tool = "Bash",
                window = "",
                control = "pytest hub/tests -q",
                action = "run_command",
                cropPng = null,
                expiresAt = 0.0,
                detail = "pytest hub/tests -q\nThư mục: D:\\turbo-desktop",
                source = "claude_code",
            )
        )
        show { ApprovalsTab(rule.activity) }
        rule.onNodeWithTag("approval").assertIsDisplayed()
        rule.onNodeWithTag("ccSourceChip").assertIsDisplayed()
        rule.onNodeWithText("Claude Code").assertIsDisplayed()
        rule.onNodeWithTag("approvalDetail").assertIsDisplayed().assertTextContains("pytest hub/tests -q", substring = true)
        rule.onNodeWithText(str(R.string.appr_no_timeout)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.appr_timeout)).assertDoesNotExist()
        Graph.pending.value = emptyList()
    }

    @Test fun fullScreenPlayerOpensWithZoomableScreen() {
        Graph.stopped.value = false
        Graph.screenViewEnabled.value = true
        Graph.screenBitmap.value = androidx.compose.ui.graphics.ImageBitmap(16, 9)
        show { WorkTab(activity = rule.activity) }
        rule.onNodeWithTag("screenPlayer").assertIsDisplayed()
        rule.onNodeWithTag("playerFullscreen").performClick()
        rule.waitForIdle()
        rule.onNodeWithTag("fullScreenPlayer").assertIsDisplayed()
        rule.onNodeWithTag("zoomableScreen").assertIsDisplayed()
        Graph.screenBitmap.value = null
    }

    @Test fun reportTabShowsOverviewAndLogTabs() {
        Graph.report.value = ReportData(
            periodDays = 7,
            days = listOf(ReportDay("2026-11-18", done = 2, failed = 0, stopped = 1, seconds = 120)),
            totals = ReportTotals(done = 2, failed = 0, stopped = 1, seconds = 120, tokensIn = 1000, tokensOut = 200, costUsd = 0.02),
            topApps = listOf(ReportApp("Calculator", 3)),
        )
        Graph.auditOk.value = true
        Graph.audit.value = emptyList()
        show { ReportTab() }
        rule.onNodeWithText(str(R.string.report_seg_overview)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.report_seg_log)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.report_p_today)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.report_p_7d)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.report_p_30d)).assertIsDisplayed()
        rule.onNodeWithTag("reportChart").assertIsDisplayed()
        rule.onNodeWithText(str(R.string.report_seg_log)).performClick()
        rule.waitForIdle()
        rule.onNodeWithText(str(R.string.audit_f_all)).assertIsDisplayed()
        rule.onNodeWithText(str(R.string.audit_f_approvals)).assertIsDisplayed()
        Graph.report.value = null
    }
}
