package dev.turbodesktop.remote

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.isImeVisible
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import kotlinx.coroutines.delay

@Composable
fun App(activity: FragmentActivity) = TurboTheme {
    var paired by remember { mutableStateOf(Graph.prefs.paired) }
    var onboarded by remember { mutableStateOf(Graph.prefs.onboarded) }
    val needs by Graph.needs.collectAsState()
    val enrollPending by Graph.totpEnrollPending.collectAsState()
    var inTotpFlow by remember { mutableStateOf(Graph.totpEnrollPending.value && Graph.needs.value.totp) }
    LaunchedEffect(enrollPending, needs.totp) {
        if (enrollPending && needs.totp) inTotpFlow = true
        if (!needs.totp) inTotpFlow = false
    }

    val expSec by Graph.sessionExp.collectAsState()
    val sid by Graph.sessionId.collectAsState()
    val sessionOpen by produceState(
        initialValue = sid.isNotBlank() && expSec > System.currentTimeMillis() / 1000L,
        key1 = sid,
        key2 = expSec,
    ) {
        if (sid.isBlank() || expSec <= 0L) {
            value = false
            return@produceState
        }
        val remMs = expSec * 1000L - System.currentTimeMillis()
        if (remMs <= 0L) {
            value = false
        } else {
            value = true
            delay(remMs + 250L)
            value = sid.isNotBlank() && expSec > System.currentTimeMillis() / 1000L
        }
    }

    when {
        !paired && !onboarded -> Welcome {
            onboarded = true
            Graph.prefs.onboarded = true
        }
        !paired -> PairScreen(
            activity = activity,
            onBack = {
                onboarded = false
                Graph.prefs.onboarded = false
            },
            onPaired = {
                paired = true
                if (Graph.totpEnrollPending.value && Graph.needs.value.totp) {
                    inTotpFlow = true
                }
            },
        )
        inTotpFlow && needs.totp -> TotpSetupScreen(
            activity = activity,
            fromSettings = false,
            onDone = {
                Graph.totpEnrollPending.value = false
                Graph.prefs.totpEnrollPending = false
                inTotpFlow = false
            },
        )
        !sessionOpen -> OpenSession(
            activity = activity,
            onUnpair = {
                Graph.unpairLocal()
                paired = false
            },
        )
        else -> Main(
            activity = activity,
            onUnpair = {
                Graph.unpairLocal()
                paired = false
            },
        )
    }
}

@Composable
@OptIn(ExperimentalLayoutApi::class)
fun Main(
    activity: FragmentActivity,
    onUnpair: () -> Unit,
) {
    val c = LocalTurboColors.current
    var tabName by rememberSaveable { mutableStateOf(Tab.TASKS.name) }
    val tab = remember(tabName) { Tab.entries.firstOrNull { it.name == tabName } ?: Tab.TASKS }
    var reportSegment by rememberSaveable { mutableIntStateOf(0) }
    var fullScreenPlayer by rememberSaveable { mutableStateOf(false) }
    var playerPaused by rememberSaveable { mutableStateOf(false) }
    var playerForceLive by rememberSaveable { mutableStateOf(false) }

    val rawIndicator by Graph.indicator.collectAsState()
    val running by Graph.taskRunning.collectAsState()
    val inputLocked by Graph.inputLocked.collectAsState()
    val stopped by Graph.stopped.collectAsState()
    val pending by Graph.pending.collectAsState()
    val screenViewEnabled by Graph.screenViewEnabled.collectAsState()
    val reducedMotion = rememberReducedMotion()

    LaunchedEffect(running) {
        if (running) playerPaused = false else playerForceLive = false
    }
    LaunchedEffect(stopped) {
        if (stopped) playerForceLive = false
    }
    LaunchedEffect(screenViewEnabled) {
        if (!screenViewEnabled) fullScreenPlayer = false
    }
    val fsRequest by Graph.requestFullScreen.collectAsState()
    LaunchedEffect(fsRequest) {   // debug/adb hook
        if (fsRequest) { fullScreenPlayer = true; Graph.requestFullScreen.value = false }
    }

    val effectiveIndicator = when {
        inputLocked || rawIndicator == "input_locked" -> "input_locked"
        rawIndicator == "acting" || running -> "acting"
        else -> rawIndicator
    }

    // Perf (measured on the owner's phone): an always-running infinite transition read during composition made the
    // whole Main recompose and redraw every frame (~11 fps idle, ~64 fps while viewing the PC). Run it only while the
    // AI is acting, and read the value inside the draw lambda so only the edge redraws.
    val pulseState: State<Float>? = if (!reducedMotion && effectiveIndicator == "acting" && !stopped) {
        val transition = rememberInfiniteTransition(label = "edgeBreathe")
        transition.animateFloat(
            initialValue = 0.38f,
            targetValue = 1f,
            animationSpec = infiniteRepeatable(
                animation = tween(durationMillis = TurboMotion.EDGE_HALF_CYCLE_MS, easing = FastOutSlowInEasing),
                repeatMode = RepeatMode.Reverse,
            ),
            label = "edgeAlpha",
        )
    } else null

    val wantedTab by Graph.requestTab.collectAsState()
    LaunchedEffect(wantedTab) {
        wantedTab?.let { name ->
            when (name.uppercase()) {
                "TASKS", "LIVE" -> tabName = Tab.TASKS.name
                "APPROVALS" -> tabName = Tab.APPROVALS.name
                "REPORT" -> {
                    reportSegment = 0
                    tabName = Tab.REPORT.name
                }
                "AUDIT" -> {
                    reportSegment = 1
                    tabName = Tab.REPORT.name
                }
                "SETTINGS" -> tabName = Tab.SETTINGS.name
            }
            fullScreenPlayer = false
            Graph.requestTab.value = null
        }
    }
    LaunchedEffect(Unit) {
        Graph.refreshTasks()
    }

    val aiColor = c.ai
    val edgeModifier = when {
        stopped -> Modifier
        effectiveIndicator == "input_locked" -> Modifier.drawWithContent {
            drawContent()
            val glowW = 18.dp.toPx()
            val crispW = 6.dp.toPx()
            drawRoundRect(
                color = aiColor.copy(alpha = 0.28f),
                topLeft = Offset(glowW / 2f, glowW / 2f),
                size = Size((size.width - glowW).coerceAtLeast(0f), (size.height - glowW).coerceAtLeast(0f)),
                cornerRadius = CornerRadius(20.dp.toPx(), 20.dp.toPx()),
                style = Stroke(width = glowW),
            )
            drawRect(
                color = aiColor,
                topLeft = Offset(crispW / 2f, crispW / 2f),
                size = Size((size.width - crispW).coerceAtLeast(0f), (size.height - crispW).coerceAtLeast(0f)),
                style = Stroke(width = crispW),
            )
        }
        effectiveIndicator == "acting" -> Modifier.drawWithContent {
            drawContent()
            val glowW = 14.dp.toPx()
            val crispW = 3.dp.toPx()
            drawRoundRect(
                color = aiColor.copy(alpha = 0.22f * (pulseState?.value ?: 1f)),
                topLeft = Offset(glowW / 2f, glowW / 2f),
                size = Size((size.width - glowW).coerceAtLeast(0f), (size.height - glowW).coerceAtLeast(0f)),
                cornerRadius = CornerRadius(22.dp.toPx(), 22.dp.toPx()),
                style = Stroke(width = glowW),
            )
            drawRect(
                color = aiColor.copy(alpha = pulseState?.value ?: 1f),
                topLeft = Offset(crispW / 2f, crispW / 2f),
                size = Size((size.width - crispW).coerceAtLeast(0f), (size.height - crispW).coerceAtLeast(0f)),
                style = Stroke(width = crispW),
            )
        }
        else -> Modifier
    }

    CompositionLocalProvider(LocalInMainShell provides true) {
        if (fullScreenPlayer && screenViewEnabled) {
            FullScreenPlayerOverlay(
                activity = activity,
                userPaused = playerPaused,
                forceLive = playerForceLive,
                onTogglePause = {
                    val liveNow = (running && !playerPaused) || playerForceLive
                    if (liveNow) {
                        playerForceLive = false
                        playerPaused = true
                    } else {
                        playerPaused = false
                        if (!running) playerForceLive = true
                    }
                },
                onClose = { fullScreenPlayer = false },
            )
        } else {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .then(edgeModifier)
                    .testTag("frame_$effectiveIndicator"),
            ) {
                // The composer sits at the bottom of the Việc screen: pad by the keyboard so it stays above it
                // (edge-to-edge: adjustResize alone does not move Compose content).
                val imeVisible = WindowInsets.isImeVisible
                Column(Modifier.fillMaxSize().imePadding()) {
                    PresenceHeader()
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth(),
                    ) {
                        when (tab) {
                            Tab.TASKS -> WorkTab(
                                activity = activity,
                                playerPaused = playerPaused,
                                playerForceLive = playerForceLive,
                                onTogglePlayerPause = {
                                    val liveNow = (running && !playerPaused) || playerForceLive
                                    if (liveNow) {
                                        playerForceLive = false
                                        playerPaused = true
                                    } else {
                                        playerPaused = false
                                        if (!running) playerForceLive = true
                                    }
                                },
                                onOpenFullScreen = { fullScreenPlayer = true },
                            )
                            Tab.APPROVALS -> ApprovalsTab(activity)
                            Tab.REPORT -> ReportTab(
                                selectedSegment = reportSegment,
                                onSelectSegment = { reportSegment = it },
                            )
                            Tab.SETTINGS -> SettingsTab(activity, onUnpair)
                        }
                    }
                    if (!imeVisible) TurboNavBar(
                        active = tab,
                        pendingCount = pending.size,
                        onSelect = { next ->
                            if (next != Tab.TASKS) playerForceLive = false
                            tabName = next.name
                        },
                    )
                }
            }
        }
    }
}
