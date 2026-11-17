package dev.turbodesktop.remote

import android.content.Context
import android.content.pm.ActivityInfo
import android.content.res.Resources
import android.graphics.BitmapFactory
import android.webkit.CookieManager
import android.webkit.WebView
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.displayCutout
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.Assignment
import androidx.compose.material.icons.automirrored.rounded.FormatListBulleted
import androidx.compose.material.icons.automirrored.rounded.OpenInNew
import androidx.compose.material.icons.rounded.ArrowUpward
import androidx.compose.material.icons.rounded.BarChart
import androidx.compose.material.icons.rounded.BatterySaver
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Cloud
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.DesktopWindows
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.Fingerprint
import androidx.compose.material.icons.rounded.Flag
import androidx.compose.material.icons.rounded.Fullscreen
import androidx.compose.material.icons.rounded.FullscreenExit
import androidx.compose.material.icons.rounded.GppMaybe
import androidx.compose.material.icons.rounded.Key
import androidx.compose.material.icons.rounded.Keyboard
import androidx.compose.material.icons.rounded.Language
import androidx.compose.material.icons.rounded.LinkOff
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.LockOpen
import androidx.compose.material.icons.rounded.Mouse
import androidx.compose.material.icons.rounded.PanTool
import androidx.compose.material.icons.rounded.Password
import androidx.compose.material.icons.rounded.Pause
import androidx.compose.material.icons.rounded.PhotoCamera
import androidx.compose.material.icons.rounded.PlayArrow
import androidx.compose.material.icons.rounded.QrCodeScanner
import androidx.compose.material.icons.rounded.RadioButtonChecked
import androidx.compose.material.icons.rounded.RadioButtonUnchecked
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material.icons.rounded.Smartphone
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material.icons.rounded.StopCircle
import androidx.compose.material.icons.rounded.SwapVert
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material.icons.rounded.TouchApp
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material.icons.rounded.VerifiedUser
import androidx.compose.material.icons.rounded.Videocam
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material.icons.rounded.WebAsset
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale
import kotlin.math.roundToLong

// ============================================================================================ 08 Stopped card
@Composable
fun StopCard(modifier: Modifier = Modifier) {
    val c = LocalTurboColors.current
    Column(
        modifier = modifier
            .fillMaxWidth()
            .testTag("stopCard")
            .padding(vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            modifier = Modifier
                .size(80.dp)
                .clip(TurboRadii.full)
                .background(c.stopContainer),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = Icons.Rounded.StopCircle,
                contentDescription = null,
                tint = c.stopText,
                modifier = Modifier.size(40.dp),
            )
        }
        Spacer(Modifier.height(14.dp))
        Text(
            text = stringResource(R.string.stop_title),
            style = MaterialTheme.typography.headlineSmall,
            color = c.onSurface,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = stringResource(R.string.stop_sub),
            style = MaterialTheme.typography.bodyMedium,
            color = c.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(horizontal = 16.dp),
        )
        Spacer(Modifier.height(20.dp))
        PrimaryButton(
            text = stringResource(R.string.stop_resume),
            leadingIcon = Icons.Rounded.PlayArrow,
            color = c.inverse,
            fg = c.onInverse,
            modifier = Modifier.testTag("resume"),
        ) {
            Graph.scope.launch { Graph.resume() }
        }
        Spacer(Modifier.height(20.dp))
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(TurboRadii.large)
                .background(c.surfaceContainer)
                .padding(TurboSpacing.cardPadding),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Rounded.Keyboard,
                    contentDescription = null,
                    tint = c.onSurfaceVariant,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    text = stringResource(R.string.stop_hotkey_card),
                    style = MaterialTheme.typography.bodySmall,
                    color = c.onSurfaceVariant,
                )
            }
            KeycapRow(keys = listOf("Ctrl", "Alt", "Shift", "K"))
        }
    }
}

// ============================================================================================ Foreground & Screen Player (12-15)
@Composable
private fun rememberIsForeground(): Boolean {
    val lifecycleOwner = LocalLifecycleOwner.current
    var foreground by remember(lifecycleOwner) {
        mutableStateOf(lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED))
    }
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, _ ->
            foreground = lifecycleOwner.lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    return foreground
}

private fun formatFps(fps: Double): String =
    if (fps % 1.0 == 0.0) fps.toInt().toString() else "%.1f".format(fps)

@Composable
private fun ScreenPollerEffect(
    enabled: Boolean,
    isLive: Boolean,
    userPaused: Boolean,
    maxFps: Double,
) {
    val isForeground = rememberIsForeground()
    val sid by Graph.sessionId.collectAsState()
    val expSec by Graph.sessionExp.collectAsState()
    val active = enabled && !userPaused && isForeground && sid.isNotBlank() && expSec > System.currentTimeMillis() / 1000L

    LaunchedEffect(active, isLive, maxFps) {
        if (!active) return@LaunchedEffect
        val minIntervalMs = (1000.0 / maxFps.coerceAtLeast(0.2)).toLong().coerceAtLeast(120L) + 25L
        if (isLive) {
            while (isActive) {
                val t0 = System.currentTimeMillis()
                val code = Graph.fetchScreenFrame()
                if (code == 403 || code == 401 || code == 302) break
                val elapsed = System.currentTimeMillis() - t0
                val waitMs = when {
                    code == -1 -> 30_000L
                    code == 429 -> minIntervalMs
                    else -> (minIntervalMs - elapsed).coerceAtLeast(40L)
                }
                delay(waitMs)
            }
        } else {
            // Idle: refresh once on open, then every 10 s.
            while (isActive) {
                val code = Graph.fetchScreenFrame()
                if (code == 403 || code == 401 || code == 302) break
                val waitMs = when {
                    code == -1 -> 30_000L
                    code == 429 && Graph.screenFrame.value == null -> minIntervalMs
                    else -> 10_000L
                }
                delay(waitMs)
            }
        }
    }
}

@Composable
private fun PlayerOverlayPill(
    text: String,
    modifier: Modifier = Modifier,
    dotColor: Color? = null,
    icon: ImageVector? = null,
) {
    val c = LocalTurboColors.current
    Row(
        modifier = modifier
            .clip(TurboRadii.full)
            .background(c.playerPillBg)
            .padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (dotColor != null) {
            Box(
                Modifier
                    .size(8.dp)
                    .clip(TurboRadii.full)
                    .background(dotColor)
            )
            Spacer(Modifier.width(6.dp))
        }
        if (icon != null) {
            Icon(
                imageVector = icon,
                contentDescription = null,
                tint = c.onSurface,
                modifier = Modifier.size(14.dp),
            )
            Spacer(Modifier.width(6.dp))
        }
        Text(
            text = text,
            style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold),
            color = c.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

private val SCREEN_FPS_CHOICES = listOf(0.5, 1.0, 2.0, 3.0, 5.0)

/** Lists the refresh rates; rates above the PC's limit are shown disabled with that limit. */
@Composable
private fun FpsChoices(onPicked: () -> Unit) {
    val c = LocalTurboColors.current
    val userFps by Graph.screenFps.collectAsState()
    val hubMax by Graph.screenViewMaxFps.collectAsState()
    SCREEN_FPS_CHOICES.forEach { f ->
        val allowed = f <= hubMax + 1e-9
        val selected = kotlin.math.abs(f - minOf(userFps, hubMax)) < 1e-9
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = TurboSpacing.touchMin)
                .clickable(enabled = allowed, role = Role.RadioButton) { Graph.setScreenFps(f); onPicked() }
                .padding(horizontal = 20.dp)
                .testTag("fps_" + formatFps(f)),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.player_fps_option, formatFps(f)),
                style = MaterialTheme.typography.bodyLarge,
                color = if (allowed) c.onSurface else c.onSurfaceVariant.copy(alpha = 0.5f),
                modifier = Modifier.weight(1f),
            )
            if (!allowed) Text(
                text = stringResource(R.string.player_fps_over_limit, formatFps(hubMax)),
                style = MaterialTheme.typography.labelMedium,
                color = c.onSurfaceVariant,
            )
            if (selected) Icon(Icons.Rounded.Check, contentDescription = null, tint = c.primary)
        }
    }
}

@Composable
private fun FpsMenuButton(modifier: Modifier = Modifier) {
    val c = LocalTurboColors.current
    val userFps by Graph.screenFps.collectAsState()
    val hubMax by Graph.screenViewMaxFps.collectAsState()
    var open by remember { mutableStateOf(false) }
    Box(modifier) {
        Box(
            modifier = Modifier
                .heightIn(min = TurboSpacing.touchMin)
                .clip(TurboRadii.full)
                .clickable(role = Role.Button, onClickLabel = stringResource(R.string.cd_player_fps)) { open = true }
                .testTag("playerFps"),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                modifier = Modifier
                    .height(36.dp)
                    .clip(TurboRadii.full)
                    .background(c.playerPillBg)
                    .padding(horizontal = 10.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    text = stringResource(R.string.player_fps_short, formatFps(minOf(userFps, hubMax))),
                    style = MaterialTheme.typography.labelMedium,
                    color = c.onSurface,
                )
            }
        }
        androidx.compose.material3.DropdownMenu(
            expanded = open,
            onDismissRequest = { open = false },
            containerColor = c.surfaceContainerLow,
        ) {
            Text(
                text = stringResource(R.string.player_fps_title),
                style = MaterialTheme.typography.labelLarge,
                color = c.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
            )
            Column(Modifier.widthIn(min = 220.dp)) { FpsChoices(onPicked = { open = false }) }
        }
    }
}

@Composable
private fun PlayerRoundIconButton(
    icon: ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    circleSizeDp: Int = 36,
) {
    val c = LocalTurboColors.current
    Box(
        modifier = modifier
            .size(TurboSpacing.touchMin)
            .clip(TurboRadii.full)
            .clickable(role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .size(circleSizeDp.dp)
                .clip(TurboRadii.full)
                .background(c.playerPillBg),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = icon,
                contentDescription = contentDescription,
                tint = c.onSurface,
                modifier = Modifier.size(20.dp),
            )
        }
    }
}

@Composable
private fun InlineScreenPlayer(
    isLive: Boolean,
    userPaused: Boolean,
    maxFps: Double,
    isActingOrLocked: Boolean,
    onTogglePause: () -> Unit,
    onOpenFullScreen: () -> Unit,
) {
    val c = LocalTurboColors.current
    val frameBytes by Graph.screenFrame.collectAsState()
    val frameAtMs by Graph.screenFrameAtMs.collectAsState()
    val redacted by Graph.screenRedacted.collectAsState()
    val online by Graph.online.collectAsState()
    val timeFmt = remember { SimpleDateFormat("HH:mm", Locale.getDefault()) }

    val bitmap = Graph.screenBitmap.collectAsState().value   // decoded off the main thread in Graph

    val redactedLabel = when {
        redacted <= 0 -> null
        redacted == 1 -> stringResource(R.string.player_redacted_one)
        else -> stringResource(R.string.player_redacted_many, redacted)
    }

    val statusPillText = when {
        isLive -> stringResource(R.string.player_live_fps, formatFps(maxFps))
        userPaused -> stringResource(R.string.player_paused)
        frameAtMs > 0L -> stringResource(R.string.player_snap_time, timeFmt.format(Date(frameAtMs)))
        online -> stringResource(R.string.player_snap_loading)
        else -> stringResource(R.string.player_snap_offline)
    }

    Box(
        modifier = Modifier
            .fillMaxWidth()
            .aspectRatio(16f / 9f)
            .testTag("screenPlayer")
            .clip(TurboRadii.medium)
            .background(c.viewfinderBg)
            .then(
                if (isActingOrLocked) Modifier.border(2.dp, c.ai, TurboRadii.medium)
                else Modifier.border(1.dp, c.outlineVariant, TurboRadii.medium)
            )
            .clickable(
                role = Role.Button,
                onClickLabel = stringResource(R.string.cd_player_fullscreen),
                onClick = onOpenFullScreen,
            ),
    ) {
        if (bitmap != null) {
            Image(
                bitmap = bitmap,
                contentDescription = stringResource(R.string.set_row_screen_view),
                contentScale = ContentScale.Crop,
                modifier = Modifier.fillMaxSize(),
            )
        } else {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Icon(
                    imageVector = Icons.Rounded.DesktopWindows,
                    contentDescription = null,
                    tint = c.outline,
                    modifier = Modifier.size(36.dp),
                )
            }
        }

        // Bottom gradient scrim for readable controls
        Box(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .height(56.dp)
                .background(
                    Brush.verticalGradient(
                        colors = listOf(Color.Transparent, c.playerScrimTop)
                    )
                )
        )

        if (redactedLabel != null) {
            PlayerOverlayPill(
                text = redactedLabel,
                icon = Icons.Rounded.VisibilityOff,
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(8.dp)
                    .testTag("redactedChip"),
            )
        }

        PlayerOverlayPill(
            text = statusPillText,
            dotColor = if (isLive) c.ai else null,
            icon = if (!isLive && frameAtMs > 0L && !userPaused) Icons.Rounded.PhotoCamera else null,
            modifier = Modifier
                .align(Alignment.BottomStart)
                .padding(start = 8.dp, bottom = 8.dp, end = 104.dp),
        )

        Row(
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(end = 2.dp, bottom = 0.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            FpsMenuButton()
            PlayerRoundIconButton(
                icon = if (isLive) Icons.Rounded.Pause else Icons.Rounded.PlayArrow,
                contentDescription = stringResource(if (isLive) R.string.cd_player_pause else R.string.cd_player_play),
                onClick = onTogglePause,
                modifier = Modifier.testTag("playerPause"),
            )
            PlayerRoundIconButton(
                icon = Icons.Rounded.Fullscreen,
                contentDescription = stringResource(R.string.cd_player_fullscreen),
                onClick = onOpenFullScreen,
                modifier = Modifier.testTag("playerFullscreen"),
            )
        }
    }
}

// ============================================================================================ 15 Full-screen landscape player
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FullScreenPlayerOverlay(
    activity: FragmentActivity,
    userPaused: Boolean,
    forceLive: Boolean,
    onTogglePause: () -> Unit,
    onClose: () -> Unit,
) {
    val c = LocalTurboColors.current
    val screenViewEnabled by Graph.screenViewEnabled.collectAsState()
    val hubMaxFps by Graph.screenViewMaxFps.collectAsState()
    val userFps by Graph.screenFps.collectAsState()
    val maxFps = minOf(userFps, hubMaxFps)
    val taskRunning by Graph.taskRunning.collectAsState()
    val stopped by Graph.stopped.collectAsState()
    val inputLocked by Graph.inputLocked.collectAsState()
    val indicator by Graph.indicator.collectAsState()
    val frameBytes by Graph.screenFrame.collectAsState()
    val frameAtMs by Graph.screenFrameAtMs.collectAsState()
    val redacted by Graph.screenRedacted.collectAsState()
    val timeFmt = remember { SimpleDateFormat("HH:mm", Locale.getDefault()) }

    val isLive = !stopped && ((taskRunning && !userPaused) || forceLive)
    val isActingOrLocked = !stopped && (inputLocked || indicator == "input_locked" || indicator == "acting" || taskRunning)

    BackHandler(onBack = onClose)

    DisposableEffect(activity) {
        val prevOrientation = activity.requestedOrientation
        activity.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        val window = activity.window
        val insets = WindowCompat.getInsetsController(window, window.decorView)
        insets.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        insets.hide(WindowInsetsCompat.Type.systemBars())
        onDispose {
            insets.show(WindowInsetsCompat.Type.systemBars())
            activity.requestedOrientation = prevOrientation
        }
    }

    ScreenPollerEffect(
        enabled = screenViewEnabled && !stopped,
        isLive = isLive,
        userPaused = userPaused,
        maxFps = maxFps,
    )

    val bitmap = Graph.screenBitmap.collectAsState().value   // decoded off the main thread in Graph

    val statusPillText = when {
        isLive -> stringResource(R.string.player_live_fps, formatFps(maxFps))
        userPaused -> stringResource(R.string.player_paused)
        frameAtMs > 0L -> stringResource(R.string.player_snap_time, timeFmt.format(Date(frameAtMs)))
        else -> stringResource(R.string.player_snap_loading)
    }

    val redactedLabel = when {
        redacted <= 0 -> null
        redacted == 1 -> stringResource(R.string.player_redacted_one)
        else -> stringResource(R.string.player_redacted_many, redacted)
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black)
            .testTag("fullScreenPlayer"),
        contentAlignment = Alignment.Center,
    ) {
        if (bitmap != null) {
            Image(
                bitmap = bitmap,
                contentDescription = stringResource(R.string.set_row_screen_view),
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxSize()
                    .then(if (isActingOrLocked) Modifier.border(3.dp, c.ai) else Modifier),
            )
        } else {
            Icon(
                imageVector = Icons.Rounded.DesktopWindows,
                contentDescription = null,
                tint = c.outline,
                modifier = Modifier.size(48.dp),
            )
        }

        // Top & bottom scrims
        Box(
            modifier = Modifier
                .align(Alignment.TopCenter)
                .fillMaxWidth()
                .height(72.dp)
                .background(Brush.verticalGradient(listOf(c.playerScrimTop, Color.Transparent)))
        )
        Box(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .height(80.dp)
                .background(Brush.verticalGradient(listOf(Color.Transparent, c.playerScrimBottom)))
        )

        // Safe-area HUD container so landscape camera cutouts never obscure buttons or pills
        Box(
            modifier = Modifier
                .fillMaxSize()
                .windowInsetsPadding(WindowInsets.displayCutout),
        ) {
            // Top-left close button
            PlayerRoundIconButton(
                icon = Icons.Rounded.Close,
                contentDescription = stringResource(R.string.btn_close),
                onClick = onClose,
                circleSizeDp = 40,
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(12.dp),
            )

            // Top-right STOP button
            if (!stopped) {
                Button(
                    onClick = { Graph.scope.launch { Graph.stop() } },
                    modifier = Modifier
                        .align(Alignment.TopEnd)
                        .padding(14.dp)
                        .defaultMinSize(minHeight = TurboSpacing.touchMin)
                        .testTag("stop"),
                    shape = TurboRadii.full,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = c.stop,
                        contentColor = c.onStop,
                    ),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 10.dp),
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Stop,
                        contentDescription = null,
                        modifier = Modifier.size(20.dp),
                    )
                    Spacer(Modifier.width(4.dp))
                    Text(
                        text = stringResource(R.string.stop),
                        fontFamily = BeVietnamPro,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp,
                        letterSpacing = 1.2.sp,
                    )
                }
            }

            // Bottom-left status + redacted pills (FlowRow wraps cleanly at 200% font scale)
            FlowRow(
                modifier = Modifier
                    .align(Alignment.BottomStart)
                    .padding(start = 16.dp, bottom = 14.dp, end = 128.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                PlayerOverlayPill(
                    text = statusPillText,
                    dotColor = if (isLive) c.ai else null,
                    icon = if (!isLive && frameAtMs > 0L && !userPaused) Icons.Rounded.PhotoCamera else null,
                )
                if (redactedLabel != null) {
                    PlayerOverlayPill(
                        text = redactedLabel,
                        icon = Icons.Rounded.VisibilityOff,
                        modifier = Modifier.testTag("redactedChip"),
                    )
                }
            }

            // Bottom-right exit full screen + pause/play
            Row(
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(end = 12.dp, bottom = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                PlayerRoundIconButton(
                    icon = Icons.Rounded.FullscreenExit,
                    contentDescription = stringResource(R.string.cd_player_exit_fullscreen),
                    onClick = onClose,
                    circleSizeDp = 42,
                )
                FpsMenuButton()
                PlayerRoundIconButton(
                    icon = if (isLive) Icons.Rounded.Pause else Icons.Rounded.PlayArrow,
                    contentDescription = stringResource(if (isLive) R.string.cd_player_pause else R.string.cd_player_play),
                    onClick = onTogglePause,
                    circleSizeDp = 42,
                )
            }
        }
    }
}

// ============================================================================================ 12-14 Merged "Việc" screen
private data class CompactStep(
    val id: String,
    val icon: ImageVector,
    val label: String,
    val time: String,
    val isError: Boolean = false,
    val isCurrent: Boolean = false,
    val isReadWindowGroup: Boolean = false,
    val count: Int = 1,
)

private data class StepSummaryResult(
    val groupedSteps: List<CompactStep>,
    val rawStepCount: Int,
    val finalAnswer: String?,
    val finalOk: Boolean,
)

private fun presentActionVerb(ctx: Context, action: String): String = ctx.getString(
    when (action) {
        "click" -> R.string.act_click
        "invoke" -> R.string.act_invoke
        "type" -> R.string.act_type
        "set_value" -> R.string.act_set_value
        "select" -> R.string.act_select
        "toggle" -> R.string.act_toggle
        "press_keys" -> R.string.act_press_keys
        else -> R.string.act_other
    }
)

private fun cleanToolName(raw: String): String =
    raw.substringAfterLast("__").replace('_', ' ').trim().ifBlank { raw }

private fun buildCompactSteps(
    ctx: Context,
    scopedEvents: List<Ev>,
    taskRunning: Boolean,
): StepSummaryResult {
    val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
    fun fmtTs(e: Ev): String {
        val ts = e.json.optDouble("ts", 0.0)
        return if (ts > 0.0) timeFmt.format(Date((ts * 1000).toLong())) else ""
    }

    val resolvedIds = scopedEvents.asSequence()
        .filter { it.type == "approval_resolved" }
        .map { it.json.optString("approval_id") }
        .toSet()

    val rows = ArrayList<CompactStep>()
    var rawCount = 0
    var pendingCall: Ev? = null
    var answerText: String? = null
    var answerOk = true

    for (e in scopedEvents) {
        when (e.type) {
            "tool_call" -> pendingCall = e
            "tool_result" -> {
                pendingCall = null
                rawCount++
                val ok = e.json.optBoolean("ok", true)
                val sumObj = e.json.optJSONObject("sum")
                val sumKey = sumObj?.optString("k").orEmpty()
                val toolShort = e.json.optString("tool").substringAfterLast("__")
                val isWindowRead = ok && (
                    sumKey in setOf("read_controls", "read_window", "listed_windows", "read_state") ||
                        (sumKey.isEmpty() && toolShort in setOf("inspect_compact", "windows_list", "system_state"))
                    )

                if (isWindowRead) {
                    val last = rows.lastOrNull()
                    if (last != null && last.isReadWindowGroup) {
                        val nextCount = last.count + 1
                        rows[rows.lastIndex] = last.copy(
                            label = ctx.getString(R.string.step_read_window_grouped, nextCount),
                            time = fmtTs(e).ifBlank { last.time },
                            count = nextCount,
                        )
                    } else {
                        val singleLabel = if (sumKey in setOf("read_controls", "read_window") || sumKey.isEmpty()) {
                            ctx.getString(R.string.step_read_window)
                        } else {
                            e.summaryText(ctx) ?: ctx.getString(R.string.step_read_window)
                        }
                        rows += CompactStep(
                            id = "ev_${e.seq}",
                            icon = Icons.Rounded.Visibility,
                            label = singleLabel,
                            time = fmtTs(e),
                            isReadWindowGroup = true,
                            count = 1,
                        )
                    }
                } else {
                    val isStepError = !ok || sumKey == "failed"
                    val actionArg = sumObj?.optJSONArray("a")?.optString(0).orEmpty()
                    val stepIcon = when {
                        isStepError -> Icons.Rounded.Error
                        sumKey == "opened" || toolShort == "launch_app" -> Icons.AutoMirrored.Rounded.OpenInNew
                        sumKey == "screenshot" || toolShort == "screenshot" -> Icons.Rounded.PhotoCamera
                        sumKey == "waited" || sumKey == "wait_timeout" || toolShort == "wait_for" -> Icons.Rounded.Schedule
                        sumKey == "acted" && actionArg in setOf("type", "set_value", "press_keys") -> Icons.Rounded.Keyboard
                        sumKey == "acted" && actionArg == "scroll" -> Icons.Rounded.SwapVert
                        else -> Icons.Rounded.TouchApp
                    }
                    val label = e.summaryText(ctx)
                        ?: tidy(e.json.optString("summary")).ifBlank { e.line(ctx) }
                    rows += CompactStep(
                        id = "ev_${e.seq}",
                        icon = stepIcon,
                        label = label,
                        time = fmtTs(e),
                        isError = isStepError,
                    )
                }
            }
            "approval_request" -> {
                val aid = e.json.optString("approval_id")
                if (aid !in resolvedIds) {
                    rows += CompactStep(
                        id = "ev_${e.seq}",
                        icon = Icons.Rounded.GppMaybe,
                        label = e.line(ctx),
                        time = fmtTs(e),
                        isCurrent = true,
                    )
                }
            }
            "approval_resolved" -> {
                rawCount++
                rows += CompactStep(
                    id = "ev_${e.seq}",
                    icon = Icons.Rounded.GppMaybe,
                    label = e.line(ctx),
                    time = fmtTs(e),
                )
            }
            "stopped" -> {
                pendingCall = null
                rawCount++
                rows += CompactStep(
                    id = "ev_${e.seq}",
                    icon = Icons.Rounded.StopCircle,
                    label = ctx.getString(R.string.ev_stopped_clean),
                    time = fmtTs(e),
                    isError = true,
                )
            }
            "final" -> {
                pendingCall = null
                val ok = e.json.optBoolean("ok", true)
                val full = e.json.optString("text").takeIf { it != "null" }.orEmpty().trim()
                if (full.isNotEmpty()) {
                    answerText = full
                    answerOk = ok
                }
            }
        }
    }

    if (taskRunning && pendingCall != null) {
        val pc = pendingCall!!
        rawCount++
        val ctrl = pc.json.optString("control").takeIf { it != "null" }.orEmpty()
        val act = pc.json.optString("action").takeIf { it != "null" }.orEmpty()
        val tool = cleanToolName(pc.json.optString("tool"))
        val title = if (ctrl.isNotBlank()) {
            ctx.getString(R.string.live_acting_step, presentActionVerb(ctx, act), ctrl)
        } else {
            ctx.getString(R.string.live_acting_tool, tool)
        }
        rows += CompactStep(
            id = "ev_call_${pc.seq}",
            icon = Icons.Rounded.TouchApp,
            label = title,
            time = fmtTs(pc),
            isCurrent = true,
        )
    }

    return StepSummaryResult(
        groupedSteps = rows,
        rawStepCount = rawCount,
        finalAnswer = answerText,
        finalOk = answerOk,
    )
}

private fun fmtDurationCompact(sec: Long): String {
    val safe = sec.coerceAtLeast(0L)
    return "%d:%02d".format(safe / 60L, safe % 60L)
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun WorkTab(
    activity: FragmentActivity? = null,
    playerPaused: Boolean = false,
    playerForceLive: Boolean = false,
    onTogglePlayerPause: (() -> Unit)? = null,
    onOpenFullScreen: (() -> Unit)? = null,
) {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val inMainShell = LocalInMainShell.current
    val scrollState = rememberScrollState()

    val events by Graph.events.collectAsState()
    val tasks by Graph.tasks.collectAsState()
    val status by Graph.status.collectAsState()
    val stopped by Graph.stopped.collectAsState()
    val paused by Graph.paused.collectAsState()
    val inputLocked by Graph.inputLocked.collectAsState()
    val indicator by Graph.indicator.collectAsState()
    val taskRunning by Graph.taskRunning.collectAsState()
    val screenViewEnabled by Graph.screenViewEnabled.collectAsState()
    val hubMaxFps by Graph.screenViewMaxFps.collectAsState()
    val userFps by Graph.screenFps.collectAsState()
    val maxFps = minOf(userFps, hubMaxFps)
    val policy by Graph.policy.collectAsState()
    val lockRemoteState by Graph.lockRemoteTask.collectAsState()

    var localPaused by remember { mutableStateOf(false) }
    var localForceLive by remember { mutableStateOf(false) }
    var localFullScreen by remember { mutableStateOf(false) }

    LaunchedEffect(taskRunning, stopped) {
        if (taskRunning) localPaused = false else localForceLive = false
        if (stopped) localForceLive = false
    }

    val effectivePaused = if (onTogglePlayerPause != null) playerPaused else localPaused
    val effectiveForceLive = if (onTogglePlayerPause != null) playerForceLive else localForceLive
    val togglePause: () -> Unit = onTogglePlayerPause ?: {
        val liveNow = (taskRunning && !localPaused) || localForceLive
        if (liveNow) {
            localForceLive = false
            localPaused = true
        } else {
            localPaused = false
            if (!taskRunning) localForceLive = true
        }
    }

    var composerText by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var sentAfterSeq by remember { mutableLongStateOf(-1L) }
    var lastSentText by remember { mutableStateOf("") }
    var lastSentAtMs by remember { mutableLongStateOf(0L) }
    var selectedTaskId by remember { mutableStateOf<String?>(null) }
    var copiedFeedback by remember { mutableStateOf(false) }

    LaunchedEffect(sending, taskRunning) {
        if (!sending && !taskRunning) {
            lastSentAtMs = 0L
            sentAfterSeq = -1L
        }
    }

    val timerActive = (taskRunning || sending) && !stopped
    val tickSec by produceState(System.currentTimeMillis() / 1000L, timerActive) {
        value = System.currentTimeMillis() / 1000L
        if (!timerActive) return@produceState
        while (isActive) {
            delay(1000L)
            value = System.currentTimeMillis() / 1000L
        }
    }

    val timeFmt = remember { SimpleDateFormat("HH:mm", Locale.getDefault()) }

    if (localFullScreen && activity != null && screenViewEnabled && onOpenFullScreen == null) {
        FullScreenPlayerOverlay(
            activity = activity,
            userPaused = effectivePaused,
            forceLive = effectiveForceLive,
            onTogglePause = togglePause,
            onClose = { localFullScreen = false },
        )
        return
    }

    val isLiveStream = !stopped && ((taskRunning && !effectivePaused) || effectiveForceLive)
    ScreenPollerEffect(
        enabled = screenViewEnabled && !stopped,
        isLive = isLiveStream,
        userPaused = effectivePaused,
        maxFps = maxFps,
    )

    val isLocked = !stopped && (inputLocked || indicator == "input_locked")
    val isActing = !stopped && (isLocked || indicator == "acting" || taskRunning)
    val wholeTaskLock = (lockRemoteState.ifBlank {
        policy?.optString("lockRemoteTask").orEmpty()
    }.ifBlank { "whole_task" }) == "whole_task"

    // Identify active / selected task (ignoring stale task_started from an earlier run while a new send is in flight)
    val rawLastStartIdx = events.indexOfLast { it.type == "task_started" }
    val rawLastStartEv = if (rawLastStartIdx >= 0) events[rawLastStartIdx] else null
    val rawEventTaskId = rawLastStartEv?.json?.optString("task_id")?.takeIf { it.isNotBlank() && it != "null" }

    // Clear manual history selection automatically when a new task starts running
    LaunchedEffect(taskRunning, rawEventTaskId) {
        if (taskRunning) selectedTaskId = null
    }

    val selectedHistoryObj = remember(tasks, selectedTaskId) {
        selectedTaskId?.let { id -> tasks.firstOrNull { it.optString("id") == id } }
    }

    BackHandler(enabled = selectedHistoryObj != null) {
        selectedTaskId = null
    }

    val runningTaskFromList = remember(tasks, taskRunning) {
        if (taskRunning) tasks.firstOrNull { it.optString("status") == "running" } else null
    }
    val runningIdFromList = runningTaskFromList?.optString("id")?.takeIf { it.isNotBlank() }

    val awaitingNewStart = selectedHistoryObj == null && (
        (sending && (rawLastStartEv == null || rawLastStartEv.seq <= sentAfterSeq)) ||
            (runningIdFromList != null && rawEventTaskId != null && runningIdFromList != rawEventTaskId)
        )

    val latestStartEv = if (awaitingNewStart) null else rawLastStartEv
    val latestEventTaskId = latestStartEv?.json?.optString("task_id")?.takeIf { it.isNotBlank() && it != "null" }

    val activeTaskObj = remember(tasks, selectedHistoryObj, runningTaskFromList, latestEventTaskId, awaitingNewStart) {
        when {
            selectedHistoryObj != null -> selectedHistoryObj
            runningTaskFromList != null -> runningTaskFromList
            awaitingNewStart -> null
            latestEventTaskId != null -> tasks.firstOrNull { it.optString("id") == latestEventTaskId }
            else -> null
        }
    }

    val scopedEvents = remember(events, selectedHistoryObj, awaitingNewStart, runningIdFromList, rawLastStartIdx) {
        val selId = selectedHistoryObj?.optString("id")?.takeIf { it.isNotBlank() }
        when {
            selId != null -> events.filter { it.json.optString("task_id") == selId }
            awaitingNewStart -> if (runningIdFromList != null) {
                events.filter { it.json.optString("task_id") == runningIdFromList }
            } else {
                emptyList()
            }
            rawLastStartIdx >= 0 -> events.subList(rawLastStartIdx, events.size)
            else -> events
        }
    }

    val hasProgressAfterSend = remember(scopedEvents) {
        scopedEvents.any {
            it.type in setOf("text", "tool_call", "tool_result", "approval_request", "final", "task_finished", "stopped")
        }
    }

    val waitingForWarmup = !stopped && selectedHistoryObj == null &&
        (sending || taskRunning) && !hasProgressAfterSend
    var showWarmup by remember { mutableStateOf(false) }

    LaunchedEffect(waitingForWarmup, lastSentAtMs) {
        if (!waitingForWarmup) {
            showWarmup = false
        } else {
            val evStartMs = latestStartEv?.json?.optDouble("ts", 0.0)?.let { if (it > 0) (it * 1000).toLong() else 0L } ?: 0L
            val refMs = if (lastSentAtMs > 0L) lastSentAtMs else evStartMs
            val elapsed = if (refMs > 0L) (System.currentTimeMillis() - refMs).coerceAtLeast(0L) else 0L
            val waitMs = (3000L - elapsed).coerceAtLeast(0L)
            if (waitMs > 0L) delay(waitMs)
            showWarmup = true
        }
    }

    val stepSummary = remember(scopedEvents, taskRunning, selectedHistoryObj, ctx) {
        buildCompactSteps(ctx, scopedEvents, taskRunning && selectedHistoryObj == null)
    }

    val cardKey = selectedHistoryObj?.optString("id")
        ?: latestEventTaskId
        ?: runningIdFromList
        ?: if (sending) "sending_$lastSentAtMs" else "idle"
    var stepsExpanded by remember(cardKey) { mutableStateOf(false) }

    val showTaskCard = !stopped && (
        selectedHistoryObj != null ||
            latestStartEv != null ||
            sending ||
            taskRunning ||
            isLocked ||
            paused
        )

    fun submitTask(promptToRun: String) {
        val trimmed = promptToRun.trim()
        if (trimmed.isEmpty() || sending || taskRunning || stopped) return
        sending = true
        copiedFeedback = false
        selectedTaskId = null
        sentAfterSeq = events.lastOrNull()?.seq ?: 0L
        lastSentText = trimmed
        lastSentAtMs = System.currentTimeMillis()
        scope.launch {
            try {
                val ok = Graph.sendTask(trimmed)
                if (ok) {
                    if (composerText.trim() == trimmed) composerText = ""
                    Graph.refreshTasks()
                } else if (!Graph.taskRunning.value) {
                    lastSentAtMs = 0L
                    sentAfterSeq = -1L
                }
            } finally {
                sending = false
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        if (!inMainShell) {
            PresenceHeader()
        }

        // Scrollable body
        Column(
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth()
                .verticalScroll(scrollState)
                .padding(horizontal = TurboSpacing.gutter)
                .testTag("events"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (stopped) {
                StopCard()
            } else if (screenViewEnabled) {
                InlineScreenPlayer(
                    isLive = isLiveStream,
                    userPaused = effectivePaused,
                    maxFps = maxFps,
                    isActingOrLocked = isActing,
                    onTogglePause = togglePause,
                    onOpenFullScreen = {
                        if (onOpenFullScreen != null) onOpenFullScreen()
                        else if (activity != null) localFullScreen = true
                    },
                )
                if (!showTaskCard) {
                    Text(
                        text = stringResource(R.string.player_tap_fullscreen),
                        style = MaterialTheme.typography.bodySmall,
                        color = c.muted,
                    )
                }
            }

            if (showTaskCard) {
                val promptText = when {
                    selectedHistoryObj != null -> selectedHistoryObj.optString("text")
                    latestStartEv != null -> latestStartEv.json.optString("text").takeIf { it != "null" }.orEmpty()
                    activeTaskObj != null -> activeTaskObj.optString("text")
                    sending -> lastSentText
                    else -> ""
                }

                val startSec = when {
                    selectedHistoryObj != null -> selectedHistoryObj.optLong("startedAt", 0L)
                    latestStartEv != null -> latestStartEv.json.optDouble("ts", 0.0).toLong()
                    activeTaskObj != null -> activeTaskObj.optLong("startedAt", 0L)
                    lastSentAtMs > 0L -> lastSentAtMs / 1000L
                    else -> 0L
                }

                val finishedEv = scopedEvents.lastOrNull { it.type == "task_finished" }
                val finishSec = when {
                    selectedHistoryObj != null -> selectedHistoryObj.optLong("finishedAt", 0L)
                    finishedEv != null -> finishedEv.json.optDouble("ts", 0.0).toLong()
                    activeTaskObj != null -> activeTaskObj.optLong("finishedAt", 0L)
                    else -> 0L
                }

                val taskStatus = when {
                    selectedHistoryObj != null -> selectedHistoryObj.optString("status", "done")
                    sending || taskRunning -> "running"
                    finishedEv != null -> finishedEv.json.optString("status", "done")
                    activeTaskObj != null -> activeTaskObj.optString("status", "done")
                    else -> "running"
                }

                val durationSec = when {
                    startSec > 0L && taskStatus == "running" -> (tickSec - startSec).coerceAtLeast(0L)
                    startSec > 0L && finishSec >= startSec -> finishSec - startSec
                    else -> 0L
                }

                val sentHeader = if (startSec > 0L) {
                    stringResource(R.string.viec_you_sent_at, timeFmt.format(Date(startSec * 1000L)))
                } else {
                    stringResource(R.string.viec_you_sent)
                }

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(TurboRadii.large)
                        .background(c.surfaceContainer)
                        .padding(TurboSpacing.cardPadding),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    if (promptText.isNotBlank()) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = sentHeader,
                                style = MaterialTheme.typography.labelMedium,
                                color = c.muted,
                                modifier = Modifier.weight(1f),
                            )
                            if (selectedHistoryObj != null) {
                                IconButton(
                                    onClick = { selectedTaskId = null },
                                    modifier = Modifier.size(TurboSpacing.touchMin),
                                ) {
                                    Icon(
                                        imageVector = Icons.Rounded.Close,
                                        contentDescription = stringResource(R.string.btn_close),
                                        tint = c.onSurfaceVariant,
                                        modifier = Modifier.size(18.dp),
                                    )
                                }
                            }
                        }
                        Text(
                            text = promptText,
                            style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Medium),
                            color = c.onSurface,
                        )
                        HorizontalDivider(color = c.outlineVariant)
                    }

                    // Status line
                    when (taskStatus) {
                        "running" -> {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .size(16.dp)
                                        .clip(TurboRadii.full)
                                        .background(c.ai.copy(alpha = 0.25f)),
                                    contentAlignment = Alignment.Center,
                                ) {
                                    Box(
                                        Modifier
                                            .size(8.dp)
                                            .clip(TurboRadii.full)
                                            .background(if (paused) c.warn else c.ai)
                                    )
                                }
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    text = stringResource(
                                        if (paused) R.string.viec_status_paused else R.string.viec_status_running,
                                        stepSummary.rawStepCount,
                                        fmtDurationCompact(durationSec),
                                    ),
                                    style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                                    color = if (paused) c.warn else c.aiText,
                                )
                            }

                            if (showWarmup) {
                                Text(
                                    text = stringResource(R.string.live_starting),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = c.onSurfaceVariant,
                                )
                            }
                        }
                        "stopped" -> {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Rounded.StopCircle,
                                    contentDescription = null,
                                    tint = c.stopText,
                                    modifier = Modifier.size(18.dp),
                                )
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    text = if (stepSummary.rawStepCount > 0 || durationSec > 0L) {
                                        stringResource(
                                            R.string.viec_status_stopped,
                                            stepSummary.rawStepCount,
                                            fmtDurationCompact(durationSec),
                                        )
                                    } else {
                                        stringResource(R.string.viec_status_stopped_plain)
                                    },
                                    style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                                    color = c.stopText,
                                )
                            }
                        }
                        "failed" -> {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Rounded.Error,
                                    contentDescription = null,
                                    tint = c.stopText,
                                    modifier = Modifier.size(18.dp),
                                )
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    text = if (stepSummary.rawStepCount > 0 || durationSec > 0L) {
                                        stringResource(
                                            R.string.viec_status_failed,
                                            stepSummary.rawStepCount,
                                            fmtDurationCompact(durationSec),
                                        )
                                    } else {
                                        stringResource(R.string.viec_status_failed_plain)
                                    },
                                    style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                                    color = c.stopText,
                                )
                            }
                        }
                        else -> {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(
                                    imageVector = Icons.Rounded.CheckCircle,
                                    contentDescription = null,
                                    tint = c.primary,
                                    modifier = Modifier.size(18.dp),
                                )
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    text = when {
                                        stepSummary.rawStepCount > 0 -> stringResource(
                                            R.string.viec_status_done,
                                            stepSummary.rawStepCount,
                                            fmtDurationCompact(durationSec),
                                        )
                                        durationSec > 0L -> stringResource(
                                            R.string.viec_status_done_short,
                                            fmtDurationCompact(durationSec),
                                        )
                                        else -> stringResource(R.string.viec_status_done_plain)
                                    },
                                    style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                                    color = c.primary,
                                )
                            }
                        }
                    }

                    if (isLocked || (taskStatus == "running" && taskRunning && wholeTaskLock && !paused)) {
                        Row(
                            modifier = Modifier.testTag("chipLocked"),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.Lock,
                                contentDescription = null,
                                tint = c.onSurfaceVariant,
                                modifier = Modifier.size(16.dp),
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = stringResource(R.string.chip_locked),
                                style = MaterialTheme.typography.bodySmall,
                                color = c.onSurfaceVariant,
                            )
                            if (wholeTaskLock && taskRunning) {
                                Text(
                                    text = " · " + stringResource(R.string.viec_locked_suffix),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = c.onSurfaceVariant,
                                )
                            }
                        }
                    }

                    // Full answer (output) + Sao chép / Giao lại when task is finished
                    if (taskStatus != "running") {
                        val answer = stepSummary.finalAnswer
                        Text(
                            text = stringResource(R.string.live_final_label),
                            style = MaterialTheme.typography.labelMedium,
                            color = c.onSurfaceVariant,
                        )
                        Text(
                            text = answer ?: stringResource(R.string.viec_no_answer),
                            style = MaterialTheme.typography.bodyLarge,
                            color = if (answer != null) c.onSurface else c.muted,
                        )

                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            val copyTarget = answer ?: promptText
                            val copyLabel = stringResource(R.string.cd_copy)
                            Row(
                                modifier = Modifier
                                    .defaultMinSize(minHeight = TurboSpacing.touchMin)
                                    .clip(TurboRadii.full)
                                    .clickable(enabled = copyTarget.isNotBlank(), role = Role.Button) {
                                        copyPlainText(ctx, copyLabel, copyTarget)
                                        copiedFeedback = true
                                    }
                                    .padding(horizontal = 12.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Icon(
                                    imageVector = if (copiedFeedback) Icons.Rounded.Check else Icons.Rounded.ContentCopy,
                                    contentDescription = null,
                                    tint = c.primary,
                                    modifier = Modifier.size(18.dp),
                                )
                                Spacer(Modifier.width(6.dp))
                                Text(
                                    text = stringResource(if (copiedFeedback) R.string.copied_toast else R.string.cd_copy),
                                    style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                                    color = c.primary,
                                )
                            }

                            if (promptText.isNotBlank()) {
                                val canRerun = !sending && !taskRunning && !stopped
                                Row(
                                    modifier = Modifier
                                        .defaultMinSize(minHeight = TurboSpacing.touchMin)
                                        .clip(TurboRadii.full)
                                        .clickable(enabled = canRerun, role = Role.Button) {
                                            submitTask(promptText)
                                        }
                                        .padding(horizontal = 12.dp, vertical = 10.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Icon(
                                        imageVector = Icons.Rounded.Refresh,
                                        contentDescription = null,
                                        tint = if (canRerun) c.primary else c.muted,
                                        modifier = Modifier.size(18.dp),
                                    )
                                    Spacer(Modifier.width(6.dp))
                                    Text(
                                        text = stringResource(R.string.viec_rerun),
                                        style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                                        color = if (canRerun) c.primary else c.muted,
                                    )
                                }
                            }
                        }
                    }
                }
            }

            // Collapsible "Chi tiết từng bước (N)" — collapsed by default
            if (stepSummary.groupedSteps.isNotEmpty()) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(TurboRadii.medium)
                        .background(c.surfaceContainerLow),
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = TurboSpacing.touchMin)
                            .clickable(role = Role.Button) { stepsExpanded = !stepsExpanded }
                            .padding(horizontal = 16.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Rounded.FormatListBulleted,
                            contentDescription = null,
                            tint = c.onSurfaceVariant,
                            modifier = Modifier.size(20.dp),
                        )
                        Spacer(Modifier.width(12.dp))
                        Text(
                            text = stringResource(R.string.viec_step_details, stepSummary.rawStepCount),
                            style = MaterialTheme.typography.labelLarge,
                            color = c.onSurface,
                            modifier = Modifier.weight(1f),
                        )
                        Icon(
                            imageVector = if (stepsExpanded) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore,
                            contentDescription = null,
                            tint = c.onSurfaceVariant,
                            modifier = Modifier.size(22.dp),
                        )
                    }

                    if (stepsExpanded) {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(bottom = 8.dp),
                        ) {
                            stepSummary.groupedSteps.forEach { st ->
                                val rowTint = when {
                                    st.isError -> c.stopText
                                    st.isCurrent -> c.aiText
                                    else -> c.onSurface
                                }
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(horizontal = 16.dp, vertical = 8.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Icon(
                                        imageVector = st.icon,
                                        contentDescription = null,
                                        tint = when {
                                            st.isError -> c.stopText
                                            st.isCurrent -> c.aiText
                                            else -> c.onSurfaceVariant
                                        },
                                        modifier = Modifier.size(16.dp),
                                    )
                                    Spacer(Modifier.width(12.dp))
                                    Text(
                                        text = st.label,
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = rowTint,
                                        maxLines = 2,
                                        overflow = TextOverflow.Ellipsis,
                                        modifier = Modifier.weight(1f),
                                    )
                                    if (st.time.isNotBlank()) {
                                        Spacer(Modifier.width(8.dp))
                                        Text(
                                            text = st.time,
                                            style = TurboType.monoTime,
                                            color = c.muted,
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Takeover / Resume controls while running or locked
            if (!stopped) {
                if (paused) {
                    PrimaryButton(
                        text = stringResource(R.string.live_resume),
                        leadingIcon = Icons.Rounded.PlayArrow,
                        modifier = Modifier.testTag("resumePaused"),
                    ) {
                        Graph.scope.launch { Graph.resume() }
                    }
                } else if (taskRunning || isLocked) {
                    GhostButton(
                        text = stringResource(R.string.takeover_button),
                        leadingIcon = Icons.Rounded.PanTool,
                        modifier = Modifier.testTag("takeover"),
                    ) {
                        Graph.scope.launch { Graph.takeOver() }
                    }
                    Text(
                        text = stringResource(R.string.viec_takeover_hint),
                        style = MaterialTheme.typography.bodySmall,
                        color = c.muted,
                    )
                }
            }

            // Transient status message (e.g. 409 busy or 423)
            if (status.isNotBlank() && status != stringResource(R.string.st_task_sent) && status != stringResource(R.string.st_session_open)) {
                Text(
                    text = status,
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.warn,
                    modifier = Modifier.testTag("status"),
                )
            }

            // Recent tasks — NO token or cost figures
            val activeIdForFilter = activeTaskObj?.optString("id").orEmpty()
            val recent = remember(tasks, activeIdForFilter, showTaskCard) {
                if (showTaskCard && activeIdForFilter.isNotBlank()) {
                    tasks.filter { it.optString("id") != activeIdForFilter }.take(8)
                } else {
                    tasks.take(8)
                }
            }

            if (recent.isNotEmpty() || !showTaskCard) {
                Spacer(Modifier.height(4.dp))
                Text(
                    text = stringResource(R.string.home_recent),
                    style = MaterialTheme.typography.titleMedium,
                    color = c.onSurface,
                )
                if (recent.isEmpty()) {
                    Text(
                        text = stringResource(R.string.home_no_recent),
                        style = MaterialTheme.typography.bodyMedium,
                        color = c.muted,
                        modifier = Modifier.padding(bottom = 12.dp),
                    )
                } else {
                    GroupedListCard {
                        recent.forEachIndexed { idx, t ->
                            if (idx > 0) InsetDivider()
                            val id = t.optString("id")
                            val st = t.optString("status")
                            val taskText = t.optString("text")
                            val tsSec = t.optLong("finishedAt", 0L).let { if (it > 0L) it else t.optLong("startedAt", 0L) }
                            val stLabel = word(ctx, st).replaceFirstChar { it.uppercase() }
                            val metaStr = if (tsSec > 0L) {
                                "$stLabel · ${timeFmt.format(Date(tsSec * 1000L))}"
                            } else {
                                stLabel
                            }
                            val icon: ImageVector
                            val iconTint: Color
                            when (st) {
                                "done" -> { icon = Icons.Rounded.CheckCircle; iconTint = c.primary }
                                "stopped" -> { icon = Icons.Rounded.StopCircle; iconTint = c.stopText }
                                "failed" -> { icon = Icons.Rounded.Error; iconTint = c.stopText }
                                else -> { icon = Icons.Rounded.Schedule; iconTint = c.aiText }
                            }

                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .heightIn(min = TurboSpacing.rowTwoLine)
                                    .clickable(role = Role.Button) {
                                        copiedFeedback = false
                                        selectedTaskId = if (st == "running") null else id
                                        scope.launch { scrollState.animateScrollTo(0) }
                                    }
                                    .padding(horizontal = TurboSpacing.gutter, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Icon(
                                    imageVector = icon,
                                    contentDescription = null,
                                    tint = iconTint,
                                    modifier = Modifier.size(22.dp),
                                )
                                Spacer(Modifier.width(12.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(
                                        text = taskText,
                                        style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium),
                                        color = c.onSurface,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                    Spacer(Modifier.height(2.dp))
                                    Text(
                                        text = metaStr,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = c.muted,
                                    )
                                }
                                Spacer(Modifier.width(8.dp))
                                Icon(
                                    imageVector = Icons.Rounded.ChevronRight,
                                    contentDescription = null,
                                    tint = c.muted,
                                    modifier = Modifier.size(20.dp),
                                )
                            }
                        }
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
        }

        // Pinned Composer at bottom
        val composerBusy = sending || taskRunning || stopped
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(c.bg),
        ) {
            HorizontalDivider(color = c.outlineVariant)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = TurboSpacing.gutter, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (composerBusy) {
                    Row(
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = TurboSpacing.touchMin)
                            .clip(RoundedCornerShape(24.dp))
                            .background(c.surfaceContainer)
                            .border(1.dp, c.outlineVariant, RoundedCornerShape(24.dp))
                            .padding(horizontal = 16.dp, vertical = 12.dp)
                            .testTag("taskInput"),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (!stopped) {
                            CircularProgressIndicator(
                                color = c.muted,
                                strokeWidth = 2.dp,
                                modifier = Modifier.size(16.dp),
                            )
                            Spacer(Modifier.width(10.dp))
                        }
                        Text(
                            text = stringResource(
                                when {
                                    stopped -> R.string.st_stopped_hint
                                    sending -> R.string.viec_sending
                                    else -> R.string.st_task_running
                                }
                            ),
                            style = MaterialTheme.typography.bodyMedium,
                            color = c.muted,
                        )
                    }
                } else {
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = TurboSpacing.touchMin)
                            .clip(RoundedCornerShape(24.dp))
                            .background(c.surfaceContainerHigh)
                            .padding(horizontal = 16.dp, vertical = 12.dp),
                        contentAlignment = Alignment.CenterStart,
                    ) {
                        if (composerText.isEmpty()) {
                            Text(
                                text = stringResource(R.string.viec_composer_hint),
                                style = MaterialTheme.typography.bodyLarge,
                                color = c.muted,
                            )
                        }
                        BasicTextField(
                            value = composerText,
                            onValueChange = { composerText = it },
                            maxLines = 4,
                            textStyle = MaterialTheme.typography.bodyLarge.copy(color = c.onSurface),
                            cursorBrush = SolidColor(c.primary),
                            modifier = Modifier
                                .fillMaxWidth()
                                .testTag("taskInput"),
                        )
                    }
                }

                val canSend = !composerBusy && composerText.trim().isNotEmpty()
                Button(
                    onClick = { submitTask(composerText) },
                    enabled = canSend,
                    modifier = Modifier
                        .size(TurboSpacing.touchMin)
                        .testTag("sendTask"),
                    shape = TurboRadii.full,
                    colors = ButtonDefaults.buttonColors(
                        containerColor = c.primary,
                        contentColor = c.onPrimary,
                        disabledContainerColor = c.surfaceContainerHigh,
                        disabledContentColor = c.outline,
                    ),
                    contentPadding = PaddingValues(0.dp),
                ) {
                    Icon(
                        imageVector = Icons.Rounded.ArrowUpward,
                        contentDescription = stringResource(R.string.home_send),
                        modifier = Modifier.size(22.dp),
                    )
                }
            }
        }
    }
}

/** Kept as entry-point alias so standalone Compose UI tests (`show { LiveTab() }`) continue to work. */
@Composable
fun LiveTab() {
    WorkTab()
}

// ============================================================================================ 09 Approvals tab
@Composable
fun ApprovalsTab(activity: FragmentActivity) {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    val pending by Graph.pending.collectAsState()
    val needs by Graph.needs.collectAsState()
    val events by Graph.events.collectAsState()
    val tasks by Graph.tasks.collectAsState()
    val stopped by Graph.stopped.collectAsState()
    val scope = rememberCoroutineScope()
    val now by produceState(System.currentTimeMillis() / 1000.0, pending.isNotEmpty()) {
        value = System.currentTimeMillis() / 1000.0
        if (pending.isEmpty()) return@produceState   // countdowns only matter while an approval is waiting
        while (true) {
            delay(1000L)
            value = System.currentTimeMillis() / 1000.0
        }
    }

    val currentTaskText = events.lastOrNull { it.type == "task_started" }?.json?.optString("text")
        ?.takeIf { it.isNotBlank() && it != "null" }
        ?: tasks.firstOrNull { it.optString("status") == "running" }?.optString("text")
            ?.takeIf { it.isNotBlank() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = TurboSpacing.gutter),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        if (stopped) {
            StopCard()
        }

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.appr_need),
                style = MaterialTheme.typography.headlineSmall,
                color = c.onSurface,
                modifier = Modifier.weight(1f),
            )
            pending.firstOrNull()?.let { first ->
                val left = (first.expiresAt - now).toLong().coerceAtLeast(0L)
                Row(
                    modifier = Modifier
                        .clip(TurboRadii.full)
                        .background(c.warnContainer)
                        .padding(horizontal = 12.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Timer,
                        contentDescription = null,
                        tint = c.onWarnContainer,
                        modifier = Modifier.size(18.dp),
                    )
                    Spacer(Modifier.width(6.dp))
                    Text(
                        text = "%d:%02d".format(left / 60, left % 60),
                        style = TurboType.monoCode.copy(fontWeight = FontWeight.SemiBold),
                        color = c.onWarnContainer,
                    )
                }
            }
        }

        if (pending.isEmpty()) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(TurboRadii.large)
                    .background(c.surfaceContainer)
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Icon(
                    imageVector = Icons.Rounded.VerifiedUser,
                    contentDescription = null,
                    tint = c.onSurfaceVariant,
                    modifier = Modifier.size(28.dp),
                )
                Text(
                    text = stringResource(R.string.appr_none),
                    style = MaterialTheme.typography.bodyLarge,
                    color = c.onSurfaceVariant,
                    modifier = Modifier.testTag("noApprovals"),
                )
            }
        }

        pending.forEachIndexed { index, a ->
            Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("approval")
                        .clip(TurboRadii.largeIncreased)
                        .background(c.surfaceContainer)
                        .padding(TurboSpacing.cardPadding),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    if (index > 0) {
                        val left = (a.expiresAt - now).toLong().coerceAtLeast(0L)
                        Row(
                            modifier = Modifier
                                .clip(TurboRadii.full)
                                .background(c.warnContainer)
                                .padding(horizontal = 10.dp, vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Icon(
                                imageVector = Icons.Rounded.Timer,
                                contentDescription = null,
                                tint = c.onWarnContainer,
                                modifier = Modifier.size(16.dp),
                            )
                            Spacer(Modifier.width(6.dp))
                            Text(
                                text = "%d:%02d".format(left / 60, left % 60),
                                style = TurboType.monoCode,
                                color = c.onWarnContainer,
                            )
                        }
                    }

                    Text(
                        text = stringResource(R.string.appr_wants, presentActionVerb(ctx, a.action), a.control),
                        style = MaterialTheme.typography.titleLarge,
                        color = c.onSurface,
                    )

                    if (a.window.isNotBlank()) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Rounded.WebAsset,
                                contentDescription = null,
                                tint = c.onSurfaceVariant,
                                modifier = Modifier.size(18.dp),
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = stringResource(R.string.appr_in, a.window),
                                style = MaterialTheme.typography.bodyMedium,
                                color = c.onSurfaceVariant,
                            )
                        }
                    }

                    a.cropPng?.let { bytes ->
                        val bmp = remember(a.id, bytes.size) {
                            BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
                        }
                        if (bmp != null) {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .heightIn(min = 64.dp, max = 168.dp)
                                    .clip(TurboRadii.medium)
                                    .background(c.cropBg)
                                    .testTag("crop"),
                                contentAlignment = Alignment.Center,
                            ) {
                                Image(
                                    bitmap = bmp.asImageBitmap(),
                                    contentDescription = stringResource(R.string.appr_crop),
                                    contentScale = ContentScale.Fit,
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(8.dp),
                                )
                            }
                            Text(
                                text = stringResource(R.string.appr_crop),
                                style = MaterialTheme.typography.bodySmall,
                                color = c.muted,
                            )
                        }
                    }

                    HorizontalDivider(color = c.outlineVariant)

                    if (currentTaskText != null) {
                        Row(verticalAlignment = Alignment.Top) {
                            Icon(
                                imageVector = Icons.AutoMirrored.Rounded.Assignment,
                                contentDescription = null,
                                tint = c.onSurfaceVariant,
                                modifier = Modifier
                                    .padding(top = 1.dp)
                                    .size(18.dp),
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = stringResource(R.string.appr_task_ctx, currentTaskText),
                                style = MaterialTheme.typography.bodySmall,
                                color = c.onSurfaceVariant,
                            )
                        }
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Rounded.Schedule,
                            contentDescription = null,
                            tint = c.onSurfaceVariant,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = stringResource(R.string.appr_timeout),
                            style = MaterialTheme.typography.bodySmall,
                            color = c.onSurfaceVariant,
                        )
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    GhostButton(
                        text = stringResource(R.string.appr_deny),
                        leadingIcon = Icons.Rounded.Close,
                        minHeight = TurboSpacing.buttonPrimary,
                        modifier = Modifier
                            .weight(1f)
                            .testTag("deny"),
                    ) {
                        scope.launch {
                            runWithBiometricIfNeeded(activity, needs.biometric) {
                                Graph.decide(a.id, "deny")
                            }
                        }
                    }
                    PrimaryButton(
                        text = stringResource(R.string.appr_allow),
                        leadingIcon = Icons.Rounded.Check,
                        color = c.warn,
                        fg = c.onWarn,
                        modifier = Modifier
                            .weight(1f)
                            .testTag("allow"),
                    ) {
                        scope.launch {
                            runWithBiometricIfNeeded(activity, needs.biometric) {
                                Graph.decide(a.id, "allow")
                            }
                        }
                    }
                }

                if (needs.biometric) {
                    Row(
                        verticalAlignment = Alignment.Top,
                        modifier = Modifier.padding(bottom = 8.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.Fingerprint,
                            contentDescription = null,
                            tint = c.muted,
                            modifier = Modifier
                                .padding(top = 1.dp)
                                .size(18.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = stringResource(R.string.appr_bio),
                            style = MaterialTheme.typography.bodySmall,
                            color = c.muted,
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(12.dp))
    }
}

// ============================================================================================ 17-18 Báo cáo (Tổng quan + Nhật ký)
private fun fmtReportDuration(ctx: Context, seconds: Long): String = when {
    seconds <= 0L -> ctx.getString(R.string.report_time_zero)
    seconds >= 3600L -> ctx.getString(R.string.time_hm, seconds / 3600L, (seconds % 3600L) / 60L)
    seconds >= 60L -> ctx.getString(R.string.report_time_min, (seconds + 30L) / 60L)
    else -> ctx.getString(R.string.time_s, seconds)
}

private fun approxTokenNumber(tokens: Long): String {
    if (tokens < 1000L) return fmtInt(tokens)
    val roundedThousands = ((tokens.toDouble() / 1000.0).roundToLong() * 1000L).coerceAtLeast(1000L)
    return fmtInt(roundedThousands)
}

private fun shortDayLabel(ctx: Context, isoDate: String, isLast: Boolean, totalDays: Int): String {
    if (isLast) return ctx.getString(R.string.report_day_today)
    return try {
        val parsed = SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(isoDate) ?: return isoDate.takeLast(5)
        if (totalDays > 7) {
            SimpleDateFormat("dd/MM", Locale.getDefault()).format(parsed)
        } else {
            val cal = Calendar.getInstance().apply { time = parsed }
            ctx.getString(
                when (cal.get(Calendar.DAY_OF_WEEK)) {
                    Calendar.MONDAY -> R.string.report_wd_mon
                    Calendar.TUESDAY -> R.string.report_wd_tue
                    Calendar.WEDNESDAY -> R.string.report_wd_wed
                    Calendar.THURSDAY -> R.string.report_wd_thu
                    Calendar.FRIDAY -> R.string.report_wd_fri
                    Calendar.SATURDAY -> R.string.report_wd_sat
                    else -> R.string.report_wd_sun
                }
            )
        }
    } catch (_: Exception) {
        isoDate.takeLast(5)
    }
}

@Composable
fun ReportTab(
    selectedSegment: Int = 0,
    onSelectSegment: ((Int) -> Unit)? = null,
) {
    val c = LocalTurboColors.current
    val scope = rememberCoroutineScope()
    var localSeg by remember { mutableIntStateOf(selectedSegment) }
    val activeSeg = if (onSelectSegment != null) selectedSegment else localSeg
    val setSeg: (Int) -> Unit = onSelectSegment ?: { localSeg = it }
    var periodDays by remember { mutableIntStateOf(7) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = TurboSpacing.gutter),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(R.string.report_title),
                style = MaterialTheme.typography.headlineSmall,
                color = c.onSurface,
                modifier = Modifier.weight(1f),
            )
            IconButton(
                onClick = {
                    scope.launch {
                        if (activeSeg == 0) Graph.refreshReport(periodDays) else Graph.refreshAudit()
                    }
                },
                modifier = Modifier
                    .size(TurboSpacing.touchMin)
                    .testTag("auditRefresh"),
            ) {
                Box(
                    modifier = Modifier
                        .size(40.dp)
                        .clip(TurboRadii.full)
                        .background(c.surfaceContainerHigh),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = Icons.Rounded.Refresh,
                        contentDescription = stringResource(R.string.audit_refresh),
                        tint = c.onSurface,
                        modifier = Modifier.size(22.dp),
                    )
                }
            }
        }

        Spacer(Modifier.height(8.dp))

        // 2-segment control: Tổng quan (default) / Nhật ký
        val segments = listOf(
            stringResource(R.string.report_seg_overview),
            stringResource(R.string.report_seg_log),
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(TurboRadii.full)
                .border(1.dp, c.outline, TurboRadii.full),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            segments.forEachIndexed { idx, label ->
                val selected = activeSeg == idx
                if (idx > 0) {
                    Box(
                        Modifier
                            .width(1.dp)
                            .height(28.dp)
                            .background(c.outline)
                    )
                }
                Row(
                    modifier = Modifier
                        .weight(1f)
                        .heightIn(min = TurboSpacing.touchMin)
                        .clip(TurboRadii.full)
                        .background(if (selected) c.primaryContainer else Color.Transparent)
                        .selectable(
                            selected = selected,
                            role = Role.Tab,
                            onClick = { setSeg(idx) },
                        )
                        .padding(horizontal = 12.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (selected) {
                        Icon(
                            imageVector = Icons.Rounded.Check,
                            contentDescription = null,
                            tint = c.onPrimaryContainer,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(Modifier.width(6.dp))
                    }
                    Text(
                        text = label,
                        style = MaterialTheme.typography.labelLarge.copy(
                            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium,
                        ),
                        color = if (selected) c.onPrimaryContainer else c.onSurface,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }

        Spacer(Modifier.height(12.dp))

        if (activeSeg == 0) {
            ReportOverviewSection(
                periodDays = periodDays,
                onSelectPeriod = { periodDays = it },
                modifier = Modifier.weight(1f),
            )
        } else {
            AuditLogSection(
                embeddedInReport = true,
                modifier = Modifier.weight(1f),
            )
        }
    }
}

@Composable
private fun ReportOverviewSection(
    periodDays: Int,
    onSelectPeriod: (Int) -> Unit,
    modifier: Modifier = Modifier,
) {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val report by Graph.report.collectAsState()
    val loading by Graph.reportLoading.collectAsState()
    val error by Graph.reportError.collectAsState()
    val showApiCost by Graph.showApiCost.collectAsState()

    LaunchedEffect(periodDays) {
        if (Graph.sessionOpen) Graph.refreshReport(periodDays)
    }

    val periods = listOf(
        1 to R.string.report_p_today,
        7 to R.string.report_p_7d,
        30 to R.string.report_p_30d,
    )

    Column(
        modifier = modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // Period chips
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(periods) { (daysVal, labelRes) ->
                val selected = periodDays == daysVal
                Box(
                    modifier = Modifier
                        .defaultMinSize(minHeight = TurboSpacing.touchMin)
                        .selectable(
                            selected = selected,
                            role = Role.RadioButton,
                            onClick = { onSelectPeriod(daysVal) },
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    Row(
                        modifier = Modifier
                            .heightIn(min = 32.dp)
                            .clip(TurboRadii.small)
                            .background(if (selected) c.primaryContainer else Color.Transparent)
                            .then(if (!selected) Modifier.border(1.dp, c.outline, TurboRadii.small) else Modifier)
                            .padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (selected) {
                            Icon(
                                imageVector = Icons.Rounded.Check,
                                contentDescription = null,
                                tint = c.onPrimaryContainer,
                                modifier = Modifier.size(18.dp),
                            )
                            Spacer(Modifier.width(6.dp))
                        }
                        Text(
                            text = stringResource(labelRes),
                            style = MaterialTheme.typography.labelLarge,
                            color = if (selected) c.onPrimaryContainer else c.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        val currentReport = report
        if (currentReport == null) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(TurboRadii.large)
                    .background(c.surfaceContainer)
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                if (loading) {
                    CircularProgressIndicator(color = c.primary, modifier = Modifier.size(28.dp))
                    Text(
                        text = stringResource(R.string.report_loading),
                        style = MaterialTheme.typography.bodyMedium,
                        color = c.onSurfaceVariant,
                    )
                } else if (error) {
                    Text(
                        text = stringResource(R.string.report_unavailable),
                        style = MaterialTheme.typography.bodyMedium,
                        color = c.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                    )
                    GhostButton(
                        text = stringResource(R.string.totp_retry),
                        leadingIcon = Icons.Rounded.Refresh,
                    ) {
                        scope.launch { Graph.refreshReport(periodDays) }
                    }
                }
            }
            return@Column
        }

        val totals = currentReport.totals
        val tileItems = listOf(
            Triple(Icons.Rounded.CheckCircle, c.primary, fmtInt(totals.done.toLong()) to stringResource(R.string.report_tile_done)),
            Triple(Icons.Rounded.StopCircle, c.stopText, fmtInt(totals.stoppedOrFailed.toLong()) to stringResource(R.string.report_tile_failed)),
            Triple(Icons.Rounded.Schedule, c.onSurfaceVariant, fmtReportDuration(ctx, totals.seconds) to stringResource(R.string.report_tile_time)),
        )
        val largeFont = LocalDensity.current.fontScale >= 1.45f

        // 3 stat tiles (stacks cleanly at >=145% font scale so 360dp viewports never clip)
        if (largeFont) {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                tileItems.forEach { (ic, tint, numAndLabel) ->
                    val (numStr, labStr) = numAndLabel
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(TurboRadii.large)
                            .background(c.surfaceContainer)
                            .padding(horizontal = 16.dp, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            imageVector = ic,
                            contentDescription = null,
                            tint = tint,
                            modifier = Modifier.size(20.dp),
                        )
                        Spacer(Modifier.width(12.dp))
                        Text(
                            text = labStr,
                            style = MaterialTheme.typography.bodyMedium,
                            color = c.onSurfaceVariant,
                            modifier = Modifier.weight(1f),
                        )
                        Spacer(Modifier.width(12.dp))
                        Text(
                            text = numStr,
                            style = MaterialTheme.typography.titleLarge,
                            color = c.onSurface,
                        )
                    }
                }
            }
        } else {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                tileItems.forEach { (ic, tint, numAndLabel) ->
                    val (numStr, labStr) = numAndLabel
                    val numStyle = when {
                        numStr.length < 4 -> MaterialTheme.typography.headlineSmall
                        numStr.length <= 8 -> MaterialTheme.typography.titleLarge
                        else -> MaterialTheme.typography.titleMedium
                    }
                    Column(
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = 104.dp)
                            .clip(TurboRadii.large)
                            .background(c.surfaceContainer)
                            .padding(14.dp),
                        verticalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Icon(
                            imageVector = ic,
                            contentDescription = null,
                            tint = tint,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            text = numStr,
                            style = numStyle,
                            color = c.onSurface,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = labStr,
                            style = MaterialTheme.typography.bodySmall,
                            color = c.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        // Tasks-per-day Canvas bar chart
        val daysList = currentReport.days
        val maxDayTasks = daysList.maxOfOrNull { it.totalTasks } ?: 0
        val topGrid = maxOf(2, ((maxDayTasks + 1) / 2) * 2)
        val midGrid = topGrid / 2

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(TurboRadii.large)
                .background(c.surfaceContainer)
                .padding(TurboSpacing.cardPadding),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = stringResource(R.string.report_chart_title),
                style = MaterialTheme.typography.titleMedium,
                color = c.onSurface,
            )
            Text(
                text = if (currentReport.periodDays == 1) {
                    stringResource(R.string.report_chart_sub_today, totals.totalTasks)
                } else {
                    stringResource(R.string.report_chart_sub_days, currentReport.periodDays, totals.totalTasks)
                },
                style = MaterialTheme.typography.bodySmall,
                color = c.muted,
            )

            Spacer(Modifier.height(4.dp))

            val todayTasksCount = daysList.lastOrNull()?.totalTasks ?: 0
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top,
            ) {
                Column(
                    modifier = Modifier
                        .padding(top = 14.dp, end = 8.dp)
                        .height(124.dp)
                        .widthIn(min = 24.dp),
                    verticalArrangement = Arrangement.SpaceBetween,
                    horizontalAlignment = Alignment.End,
                ) {
                    Text(text = fmtInt(topGrid.toLong()), style = MaterialTheme.typography.bodySmall, color = c.muted)
                    Text(text = fmtInt(midGrid.toLong()), style = MaterialTheme.typography.bodySmall, color = c.muted)
                    Text(text = fmtInt(0L), style = MaterialTheme.typography.bodySmall, color = c.muted)
                }

                val gridColor = c.outlineVariant
                val barColor = c.chartBar
                val todayColor = c.primary

                Column(Modifier.weight(1f)) {
                    if (daysList.isNotEmpty()) {
                        if (daysList.size <= 7) {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .heightIn(min = 18.dp),
                            ) {
                                for (i in 0 until daysList.lastIndex) {
                                    Spacer(Modifier.weight(1f))
                                }
                                Text(
                                    text = if (todayTasksCount > 0 || maxDayTasks == 0) fmtInt(todayTasksCount.toLong()) else "",
                                    style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold),
                                    color = c.onSurface,
                                    textAlign = TextAlign.Center,
                                    modifier = Modifier.weight(1f),
                                )
                            }
                        } else {
                            Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .heightIn(min = 18.dp),
                                horizontalArrangement = Arrangement.End,
                            ) {
                                Text(
                                    text = if (todayTasksCount > 0 || maxDayTasks == 0) fmtInt(todayTasksCount.toLong()) else "",
                                    style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold),
                                    color = c.onSurface,
                                )
                            }
                        }
                    }
                    Canvas(
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(112.dp)
                            .testTag("reportChart"),
                    ) {
                        val h = size.height
                        val w = size.width
                        for (g in listOf(0f, 0.5f, 1f)) {
                            val gy = h - h * g
                            drawLine(gridColor, Offset(0f, gy), Offset(w, gy), strokeWidth = 1.dp.toPx())
                        }
                        if (daysList.isNotEmpty() && topGrid > 0) {
                            val count = daysList.size
                            val slotW = w / count.toFloat()
                            val barW = (slotW * 0.55f).coerceIn(4.dp.toPx(), 22.dp.toPx())
                            val cornerR = (barW / 3f).coerceAtMost(4.dp.toPx())

                            daysList.forEachIndexed { idx, day ->
                                val v = day.totalTasks
                                if (v > 0) {
                                    val barH = (h * (v.toFloat() / topGrid.toFloat())).coerceAtLeast(3.dp.toPx())
                                    val bx = idx * slotW + (slotW - barW) / 2f
                                    val topY = h - barH
                                    val r = cornerR.coerceAtMost(barH / 2f)
                                    val p = Path().apply {
                                        addRoundRect(
                                            RoundRect(
                                                rect = Rect(bx, topY, bx + barW, h),
                                                topLeft = CornerRadius(r, r),
                                                topRight = CornerRadius(r, r),
                                            )
                                        )
                                    }
                                    drawPath(
                                        path = p,
                                        color = if (idx == daysList.lastIndex) todayColor else barColor,
                                    )
                                }
                            }
                        }
                    }

                    if (daysList.isNotEmpty()) {
                        Spacer(Modifier.height(6.dp))
                        if (daysList.size <= 7) {
                            Row(Modifier.fillMaxWidth()) {
                                daysList.forEachIndexed { idx, d ->
                                    val isToday = idx == daysList.lastIndex
                                    Text(
                                        text = shortDayLabel(ctx, d.date, isToday, daysList.size),
                                        style = MaterialTheme.typography.bodySmall.copy(
                                            fontWeight = if (isToday) FontWeight.SemiBold else FontWeight.Normal,
                                        ),
                                        color = if (isToday) c.onSurface else c.muted,
                                        textAlign = TextAlign.Center,
                                        maxLines = 1,
                                        modifier = Modifier.weight(1f),
                                    )
                                }
                            }
                        } else {
                            // 30-day axis: show 5 evenly-spaced ticks + Today so labels never collide
                            val tickIndices = listOf(0, 7, 14, 21, daysList.lastIndex).distinct()
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                            ) {
                                tickIndices.forEach { idx ->
                                    val isToday = idx == daysList.lastIndex
                                    Text(
                                        text = shortDayLabel(ctx, daysList[idx].date, isToday, daysList.size),
                                        style = MaterialTheme.typography.bodySmall.copy(
                                            fontWeight = if (isToday) FontWeight.SemiBold else FontWeight.Normal,
                                        ),
                                        color = if (isToday) c.onSurface else c.muted,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        // Tokens in plain words + helper sentence + optional API cost
        Text(
            text = stringResource(R.string.report_tokens_section),
            style = MaterialTheme.typography.titleMedium,
            color = c.onSurface,
        )

        val tokenHeadline = when {
            totals.totalTokens <= 0L -> stringResource(R.string.report_tokens_zero)
            currentReport.periodDays == 1 -> stringResource(R.string.report_tokens_today, approxTokenNumber(totals.totalTokens))
            else -> stringResource(R.string.report_tokens_days, approxTokenNumber(totals.totalTokens), currentReport.periodDays)
        }

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .testTag("usage")
                .clip(TurboRadii.large)
                .background(c.surfaceContainer)
                .padding(TurboSpacing.cardPadding),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(verticalAlignment = Alignment.Top) {
                Icon(
                    imageVector = Icons.Rounded.BarChart,
                    contentDescription = null,
                    tint = c.onSurfaceVariant,
                    modifier = Modifier
                        .padding(top = 1.dp)
                        .size(20.dp),
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    text = tokenHeadline,
                    style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                    color = c.onSurface,
                )
            }
            Text(
                text = stringResource(R.string.report_tokens_helper),
                style = MaterialTheme.typography.bodySmall,
                color = c.onSurfaceVariant,
            )
            if (showApiCost) {
                Text(
                    text = stringResource(R.string.report_cost_line, "%.2f".format(totals.costUsd)),
                    style = MaterialTheme.typography.labelMedium,
                    color = c.primary,
                    modifier = Modifier.testTag("apiCostLine"),
                )
            }
        }

        // Top apps
        Text(
            text = stringResource(R.string.report_apps_section),
            style = MaterialTheme.typography.titleMedium,
            color = c.onSurface,
        )

        if (currentReport.topApps.isEmpty()) {
            Text(
                text = stringResource(R.string.report_apps_empty),
                style = MaterialTheme.typography.bodyMedium,
                color = c.muted,
                modifier = Modifier.padding(bottom = 16.dp),
            )
        } else {
            val maxAppCount = currentReport.topApps.maxOf { it.count }.coerceAtLeast(1)
            GroupedListCard {
                currentReport.topApps.forEachIndexed { idx, appItem ->
                    if (idx > 0) InsetDivider()
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = TurboSpacing.touchMin)
                            .padding(horizontal = TurboSpacing.gutter, vertical = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.WebAsset,
                            contentDescription = null,
                            tint = c.onSurfaceVariant,
                            modifier = Modifier.size(20.dp),
                        )
                        Spacer(Modifier.width(12.dp))
                        Text(
                            text = appItem.name,
                            style = MaterialTheme.typography.labelLarge,
                            color = c.onSurface,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.weight(1f),
                        )
                        Spacer(Modifier.width(12.dp))
                        Box(
                            modifier = Modifier
                                .width(88.dp)
                                .height(8.dp),
                            contentAlignment = Alignment.CenterStart,
                        ) {
                            val ratio = (appItem.count.toFloat() / maxAppCount.toFloat()).coerceIn(0.08f, 1f)
                            Box(
                                Modifier
                                    .fillMaxWidth(ratio)
                                    .fillMaxHeight()
                                    .clip(RoundedCornerShape(4.dp))
                                    .background(c.chartBar)
                            )
                        }
                        Spacer(Modifier.width(12.dp))
                        Text(
                            text = stringResource(R.string.report_app_count, appItem.count),
                            style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium),
                            color = c.onSurfaceVariant,
                        )
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
        }
    }
}

// ============================================================================================ 10 / 18 Nhật ký (Audit list)
private enum class AuditFilter(val labelRes: Int) {
    ALL(R.string.audit_f_all),
    ACTIONS(R.string.audit_f_actions),
    APPROVALS(R.string.audit_f_approvals),
    STOPS(R.string.audit_f_stops);

    fun matches(kind: String): Boolean = when (this) {
        ALL -> true
        ACTIONS -> kind in setOf("action", "tool_result", "final", "task_start", "task_end", "input_lock", "screen_view")
        APPROVALS -> kind.startsWith("approval")
        STOPS -> kind in setOf("stop", "resume", "takeover", "action_blocked", "rejected", "lockout")
    }
}

private data class FormattedAuditRow(
    val icon: ImageVector,
    val tint: Color,
    val title: String,
    val subtitle: String,
)

private fun formatAuditDevice(ctx: Context, dev: String): String {
    if (dev.isBlank() || dev == "null") return ""
    val myId = try { Graph.prefs.deviceId } catch (_: Exception) { "" }
    return when {
        myId.isNotBlank() && dev == myId -> ctx.getString(R.string.audit_this_phone)
        dev == "pc-admin" || dev == "local-admin" -> ctx.getString(R.string.audit_pc_local)
        else -> dev
    }
}

private fun formatAuditEntry(ctx: Context, c: TurboColors, entry: JSONObject): FormattedAuditRow {
    val kind = entry.optString("kind")
    val d = entry.optJSONObject("data") ?: JSONObject()
    fun s(k: String) = d.optString(k).takeIf { it != "null" }.orEmpty()

    return when (kind) {
        "stop" -> FormattedAuditRow(Icons.Rounded.StopCircle, c.stopText, ctx.getString(R.string.audit_k_stop), formatAuditDevice(ctx, s("device")))
        "resume" -> FormattedAuditRow(Icons.Rounded.PlayArrow, c.onSurfaceVariant, ctx.getString(R.string.audit_k_resume), formatAuditDevice(ctx, s("device")))
        "takeover" -> FormattedAuditRow(Icons.Rounded.PanTool, c.aiText, ctx.getString(R.string.audit_k_takeover), formatAuditDevice(ctx, s("device")))
        "task_start" -> FormattedAuditRow(Icons.AutoMirrored.Rounded.Assignment, c.onSurfaceVariant, ctx.getString(R.string.audit_k_task_start), s("text"))
        "task_end" -> FormattedAuditRow(Icons.Rounded.Flag, c.onSurfaceVariant, ctx.getString(R.string.audit_k_task_end, word(ctx, s("status"))), s("task"))
        "action" -> {
            val target = s("control").ifBlank { cleanToolName(s("tool")) }
            val sub = listOfNotNull(s("window").ifBlank { null }, cleanToolName(s("tool")).ifBlank { null }).joinToString(" · ")
            FormattedAuditRow(Icons.Rounded.TouchApp, c.onSurfaceVariant, ctx.getString(R.string.audit_k_action, target), sub)
        }
        "tool_result" -> {
            val ok = d.optBoolean("ok", true)
            val sum = tidy(s("summary")).ifBlank { cleanToolName(s("tool")) }
            val icon = if (!ok) Icons.Rounded.Error else if (s("tool").contains("launch")) Icons.AutoMirrored.Rounded.OpenInNew else Icons.Rounded.Visibility
            FormattedAuditRow(icon, if (ok) c.onSurfaceVariant else c.stopText, sum, cleanToolName(s("tool")))
        }
        "final" -> FormattedAuditRow(Icons.Rounded.CheckCircle, c.primary, ctx.getString(R.string.audit_k_final), tidy(s("summary")))
        "approval_requested" -> {
            val target = s("control").ifBlank { cleanToolName(s("tool")) }
            FormattedAuditRow(Icons.Rounded.GppMaybe, c.warn, ctx.getString(R.string.audit_k_appr_req, target), s("window"))
        }
        "approval_resolved", "approval_decision_by" -> {
            val dec = word(ctx, s("decision")).replaceFirstChar { it.uppercase() }
            val target = s("control").ifBlank { s("approval") }
            val tint = if (s("decision") == "allow") c.primary else c.warn
            val sub = listOfNotNull(
                formatAuditDevice(ctx, s("device")).ifBlank { ctx.getString(R.string.audit_you_decided) },
                cleanToolName(s("tool")).ifBlank { null },
            ).joinToString(" · ")
            FormattedAuditRow(Icons.Rounded.GppMaybe, tint, ctx.getString(R.string.audit_k_appr_res, dec, target), sub)
        }
        "input_lock" -> {
            val on = d.optBoolean("locked")
            FormattedAuditRow(Icons.Rounded.Lock, if (on) c.aiText else c.onSurfaceVariant, ctx.getString(if (on) R.string.audit_k_lock_on else R.string.audit_k_lock_off), s("mode"))
        }
        "screen_view" -> FormattedAuditRow(Icons.Rounded.Videocam, c.onSurfaceVariant, ctx.getString(R.string.audit_k_screen_view), formatAuditDevice(ctx, s("device")))
        "action_blocked" -> FormattedAuditRow(Icons.Rounded.StopCircle, c.stopText, ctx.getString(R.string.audit_k_blocked), cleanToolName(s("tool")))
        "rejected" -> FormattedAuditRow(Icons.Rounded.Error, c.stopText, ctx.getString(R.string.audit_k_rejected), listOfNotNull(s("why").ifBlank { null }, s("path").ifBlank { null }).joinToString(" · "))
        "lockout" -> FormattedAuditRow(Icons.Rounded.Lock, c.stopText, ctx.getString(R.string.audit_k_lockout), s("last"))
        "paired" -> FormattedAuditRow(Icons.Rounded.Smartphone, c.primary, ctx.getString(R.string.audit_k_paired), s("name"))
        "pairing_created" -> FormattedAuditRow(Icons.Rounded.QrCodeScanner, c.onSurfaceVariant, ctx.getString(R.string.audit_k_pair_new), "")
        "totp_enroll_opened" -> FormattedAuditRow(Icons.Rounded.Key, c.onSurfaceVariant, ctx.getString(R.string.audit_k_totp_open), "")
        "totp_enroll_fetched" -> FormattedAuditRow(Icons.Rounded.Key, c.primary, ctx.getString(R.string.audit_k_totp_fetch), formatAuditDevice(ctx, s("device")))
        "totp_rotated" -> FormattedAuditRow(Icons.Rounded.Refresh, c.warn, ctx.getString(R.string.audit_k_totp_rot), "")
        "device_revoked" -> FormattedAuditRow(Icons.Rounded.LinkOff, c.stopText, ctx.getString(R.string.audit_k_revoked), s("device"))
        "session_start" -> FormattedAuditRow(Icons.Rounded.LockOpen, c.primary, ctx.getString(R.string.audit_k_session), formatAuditDevice(ctx, s("device")))
        "agent_reaped" -> FormattedAuditRow(Icons.Rounded.Refresh, c.onSurfaceVariant, ctx.getString(R.string.audit_k_reaped), s("why"))
        else -> FormattedAuditRow(Icons.AutoMirrored.Rounded.Assignment, c.onSurfaceVariant, kind, d.toString().take(120))
    }
}

private fun isSameDay(calA: Calendar, calB: Calendar): Boolean =
    calA.get(Calendar.YEAR) == calB.get(Calendar.YEAR) &&
        calA.get(Calendar.DAY_OF_YEAR) == calB.get(Calendar.DAY_OF_YEAR)

@Composable
fun AuditTab() {
    AuditLogSection(
        embeddedInReport = false,
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = TurboSpacing.gutter),
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AuditLogSection(
    embeddedInReport: Boolean,
    modifier: Modifier = Modifier,
) {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val entries by Graph.audit.collectAsState()
    val ok by Graph.auditOk.collectAsState()
    var filter by remember { mutableStateOf(AuditFilter.ALL) }
    var selectedEntry by remember { mutableStateOf<JSONObject?>(null) }

    LaunchedEffect(Unit) {
        if (Graph.sessionOpen) Graph.refreshAudit()
    }

    val filtered = remember(entries, filter) {
        entries.filter { filter.matches(it.optString("kind")) }
    }
    val timeFmt = remember { SimpleDateFormat("HH:mm:ss", Locale.getDefault()) }
    val dateFmt = remember { SimpleDateFormat("dd/MM/yyyy", Locale.getDefault()) }

    selectedEntry?.let { entry ->
        ModalBottomSheet(
            onDismissRequest = { selectedEntry = null },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = c.surfaceContainerLow,
            scrimColor = c.scrim,
            shape = TurboRadii.extraLargeTop,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp)
                    .padding(bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(
                    text = stringResource(R.string.audit_detail_title),
                    style = MaterialTheme.typography.titleLarge,
                    color = c.onSurface,
                )
                val pretty = remember(entry) {
                    try { entry.toString(2) } catch (_: Exception) { entry.toString() }
                }
                CodeBlock(
                    command = pretty,
                    textColor = c.onSurface,
                )
                GhostButton(
                    text = stringResource(R.string.btn_close),
                    onClick = { selectedEntry = null },
                )
            }
        }
    }

    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (!embeddedInReport) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.audit_title),
                    style = MaterialTheme.typography.headlineSmall,
                    color = c.onSurface,
                    modifier = Modifier.weight(1f),
                )
                IconButton(
                    onClick = { scope.launch { Graph.refreshAudit() } },
                    modifier = Modifier
                        .size(TurboSpacing.touchMin)
                        .testTag("auditRefresh"),
                ) {
                    Box(
                        modifier = Modifier
                            .size(40.dp)
                            .clip(TurboRadii.full)
                            .background(c.surfaceContainerHigh),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.Refresh,
                            contentDescription = stringResource(R.string.audit_refresh),
                            tint = c.onSurface,
                            modifier = Modifier.size(22.dp),
                        )
                    }
                }
            }
        }

        // Hash chain integrity card
        val chainValid = ok != false
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .testTag("auditChain")
                .clip(TurboRadii.large)
                .background(if (chainValid) c.primaryContainer else c.stopContainer)
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = if (chainValid) Icons.Rounded.VerifiedUser else Icons.Rounded.Error,
                contentDescription = null,
                tint = if (chainValid) c.onPrimaryContainer else c.onStopContainer,
                modifier = Modifier.size(24.dp),
            )
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    text = if (chainValid) {
                        stringResource(R.string.audit_ok, entries.size)
                    } else {
                        stringResource(R.string.audit_bad)
                    },
                    style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                    color = if (chainValid) c.onPrimaryContainer else c.onStopContainer,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    text = stringResource(R.string.audit_foot),
                    style = MaterialTheme.typography.bodySmall,
                    color = if (chainValid) c.onPrimaryContainer else c.onStopContainer,
                )
            }
        }

        // Filter chips (48dp touch target)
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items(AuditFilter.entries) { f ->
                val selected = f == filter
                Box(
                    modifier = Modifier
                        .defaultMinSize(minHeight = TurboSpacing.touchMin)
                        .selectable(
                            selected = selected,
                            role = Role.RadioButton,
                            onClick = { filter = f },
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    Row(
                        modifier = Modifier
                            .heightIn(min = 32.dp)
                            .clip(TurboRadii.small)
                            .background(if (selected) c.primaryContainer else Color.Transparent)
                            .then(if (!selected) Modifier.border(1.dp, c.outline, TurboRadii.small) else Modifier)
                            .padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (selected) {
                            Icon(
                                imageVector = Icons.Rounded.Check,
                                contentDescription = null,
                                tint = c.onPrimaryContainer,
                                modifier = Modifier.size(18.dp),
                            )
                            Spacer(Modifier.width(6.dp))
                        }
                        Text(
                            text = stringResource(f.labelRes),
                            style = MaterialTheme.typography.labelLarge,
                            color = if (selected) c.onPrimaryContainer else c.onSurfaceVariant,
                        )
                    }
                }
            }
        }

        if (filtered.isEmpty()) {
            Box(Modifier.weight(1f).fillMaxWidth()) {
                Text(
                    text = stringResource(R.string.audit_empty),
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.muted,
                )
            }
        } else {
            val todayCal = remember { Calendar.getInstance() }
            val todayStr = stringResource(R.string.audit_today)

            LazyColumn(
                modifier = Modifier.weight(1f),
                contentPadding = PaddingValues(bottom = 12.dp),
            ) {
                filtered.forEachIndexed { idx, e ->
                    val tsMs = (e.optDouble("ts", 0.0) * 1000).toLong()
                    val prevTsMs = if (idx > 0) (filtered[idx - 1].optDouble("ts", 0.0) * 1000).toLong() else -1L
                    val curCal = Calendar.getInstance().apply { timeInMillis = tsMs }
                    val showDayHeader = tsMs > 0L && (
                        idx == 0 || prevTsMs <= 0L || !isSameDay(
                            curCal,
                            Calendar.getInstance().apply { timeInMillis = prevTsMs }
                        )
                    )

                    if (showDayHeader) {
                        val dayLabel = if (isSameDay(curCal, todayCal)) todayStr else dateFmt.format(Date(tsMs))
                        item(key = "day_${idx}_$dayLabel") {
                            Text(
                                text = dayLabel,
                                style = MaterialTheme.typography.labelMedium,
                                color = c.onSurfaceVariant,
                                modifier = Modifier.padding(top = if (idx == 0) 0.dp else 12.dp, bottom = 6.dp),
                            )
                        }
                    }

                    item(key = "audit_$idx") {
                        if (idx > 0 && !showDayHeader) {
                            HorizontalDivider(color = c.outlineVariant)
                        }
                        val row = formatAuditEntry(ctx, c, e)
                        val tm = if (tsMs > 0L) timeFmt.format(Date(tsMs)) else "--:--:--"
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .heightIn(min = 58.dp)
                                .clickable(role = Role.Button) { selectedEntry = e }
                                .padding(vertical = 10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = tm,
                                style = TurboType.monoTime,
                                color = c.muted,
                                modifier = Modifier.widthIn(min = 68.dp),
                            )
                            Spacer(Modifier.width(4.dp))
                            Icon(
                                imageVector = row.icon,
                                contentDescription = null,
                                tint = row.tint,
                                modifier = Modifier.size(20.dp),
                            )
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    text = row.title,
                                    style = MaterialTheme.typography.labelLarge,
                                    color = c.onSurface,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                if (row.subtitle.isNotBlank()) {
                                    Spacer(Modifier.height(2.dp))
                                    Text(
                                        text = row.subtitle,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = c.muted,
                                        maxLines = 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                            }
                            Spacer(Modifier.width(6.dp))
                            Icon(
                                imageVector = Icons.Rounded.ChevronRight,
                                contentDescription = null,
                                tint = c.muted,
                                modifier = Modifier.size(18.dp),
                            )
                        }
                    }
                }
            }
        }
    }
}

// ============================================================================================ 11 & 16 Settings tab + sheets
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsTab(activity: FragmentActivity, onUnpair: () -> Unit) {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val policy by Graph.policy.collectAsState()
    val needs by Graph.needs.collectAsState()
    val enrollPending by Graph.totpEnrollPending.collectAsState()
    val screenViewEnabledState by Graph.screenViewEnabled.collectAsState()
    val screenViewMaxFpsState by Graph.screenViewMaxFps.collectAsState()
    val lockRemoteTaskState by Graph.lockRemoteTask.collectAsState()
    val showApiCost by Graph.showApiCost.collectAsState()
    val wake by Graph.wakeState.collectAsState()
    val needAccessLogin by Graph.needAccessLogin.collectAsState()

    var showCf by remember { mutableStateOf(false) }
    var showTotpSetup by remember { mutableStateOf(false) }
    var showLangSheet by remember { mutableStateOf(false) }
    var showTotpSheet by remember { mutableStateOf(false) }
    var showBatterySheet by remember { mutableStateOf(false) }

    var url by remember { mutableStateOf("") }
    var relayUrl by remember { mutableStateOf(try { Graph.prefs.relayUrl } catch (_: Exception) { "" }) }
    var relayCode by remember { mutableStateOf("") }

    if (showCf) {
        CfLogin {
            Graph.needAccessLogin.value = false
            showCf = false
        }
        return
    }
    if (showTotpSetup) {
        TotpSetupScreen(
            activity = activity,
            fromSettings = true,
            onBack = { showTotpSetup = false },
            onDone = { showTotpSetup = false },
        )
        return
    }

    LaunchedEffect(Unit) {
        if (Graph.sessionOpen) Graph.refreshTasks()
    }

    val presetName = policy?.optString("preset")?.ifBlank { null }
        ?: (try { Graph.prefs.preset } catch (_: Exception) { "" }).ifBlank { "easy" }
    val effectiveLockMode = policy?.optString("lockRemoteTask")?.ifBlank { null }
        ?: policy?.optString("lockMode")?.ifBlank { null }
        ?: lockRemoteTaskState.ifBlank { "whole_task" }
    val svFromPolicy = HubJson.screenView(policy)
    val screenViewOn = svFromPolicy?.enabled ?: screenViewEnabledState
    val screenViewFpsMax = svFromPolicy?.maxFps ?: screenViewMaxFpsState
    val userFpsSetting by Graph.screenFps.collectAsState()
    val screenViewFps = minOf(userFpsSetting, screenViewFpsMax)
    var showFpsSheet by remember { mutableStateOf(false) }
    if (showFpsSheet) {
        ModalBottomSheet(
            onDismissRequest = { showFpsSheet = false },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = c.surfaceContainerLow,
            scrimColor = c.scrim,
            shape = TurboRadii.extraLargeTop,
        ) {
            Column(Modifier.fillMaxWidth().padding(bottom = 20.dp)) {
                Text(
                    text = stringResource(R.string.player_fps_title),
                    style = MaterialTheme.typography.titleLarge,
                    color = c.onSurface,
                    modifier = Modifier.padding(horizontal = 24.dp),
                )
                Text(
                    text = stringResource(R.string.player_fps_sheet_sub),
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.onSurfaceVariant,
                    modifier = Modifier.padding(start = 24.dp, end = 24.dp, top = 6.dp, bottom = 8.dp),
                )
                FpsChoices(onPicked = { showFpsSheet = false })
            }
        }
    }

    fun boolPolicy(key: String, def: Boolean): Boolean = policy?.optBoolean(key, def) ?: def

    val totpOn = boolPolicy("totp", needs.totp)
    val askOn = (policy?.optJSONArray("ask")?.length() ?: 4) > 0
    val borderOn = boolPolicy("border", true)
    val bioOn = boolPolicy("biometric", needs.biometric)
    val cfOn = boolPolicy("cfAccess", false)

    val currentLangTag = remember(ctx) { AppLang.current(ctx) }
    val currentLangLabel = when {
        currentLangTag.startsWith("vi") -> stringResource(R.string.lang_vi)
        currentLangTag.startsWith("en") -> stringResource(R.string.lang_en)
        else -> stringResource(R.string.lang_system)
    }
    val systemLangName = remember {
        val sysLoc = Resources.getSystem().configuration.locales[0] ?: Locale.getDefault()
        sysLoc.getDisplayLanguage(sysLoc).replaceFirstChar { it.uppercase() }
    }

    // 11b: Language bottom sheet
    if (showLangSheet) {
        ModalBottomSheet(
            onDismissRequest = { showLangSheet = false },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = c.surfaceContainerLow,
            scrimColor = c.scrim,
            shape = TurboRadii.extraLargeTop,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 20.dp),
            ) {
                Column(Modifier.padding(horizontal = 24.dp)) {
                    Text(
                        text = stringResource(R.string.set_lang_row),
                        style = MaterialTheme.typography.titleLarge,
                        color = c.onSurface,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        text = stringResource(R.string.lang_sheet_sub),
                        style = MaterialTheme.typography.bodyMedium,
                        color = c.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.height(12.dp))
                val options = listOf(
                    Triple("", stringResource(R.string.lang_system), stringResource(R.string.lang_device_using, systemLangName)),
                    Triple("vi", stringResource(R.string.lang_vi), null),
                    Triple("en", stringResource(R.string.lang_en), null),
                )
                options.forEach { (tag, label, sub) ->
                    val selected = if (tag.isEmpty()) currentLangTag.isBlank() else currentLangTag.startsWith(tag)
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = if (sub != null) 64.dp else 56.dp)
                            .selectable(
                                selected = selected,
                                role = Role.RadioButton,
                                onClick = {
                                    showLangSheet = false
                                    AppLang.set(activity, tag)
                                    activity.recreate()
                                },
                            )
                            .padding(horizontal = 24.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            imageVector = if (selected) Icons.Rounded.RadioButtonChecked else Icons.Rounded.RadioButtonUnchecked,
                            contentDescription = null,
                            tint = if (selected) c.primary else c.onSurfaceVariant,
                            modifier = Modifier.size(24.dp),
                        )
                        Spacer(Modifier.width(16.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                text = label,
                                style = MaterialTheme.typography.bodyLarge,
                                color = c.onSurface,
                            )
                            if (sub != null) {
                                Spacer(Modifier.height(2.dp))
                                Text(
                                    text = sub,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = c.muted,
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    // 2FA reset bottom sheet
    if (showTotpSheet) {
        ModalBottomSheet(
            onDismissRequest = { showTotpSheet = false },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = c.surfaceContainerLow,
            scrimColor = c.scrim,
            shape = TurboRadii.extraLargeTop,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp)
                    .padding(bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(
                    text = stringResource(R.string.totp_reset_title),
                    style = MaterialTheme.typography.titleLarge,
                    color = c.onSurface,
                )
                Text(
                    text = stringResource(R.string.totp_reset_explain),
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.onSurfaceVariant,
                )
                CodeBlock(command = stringResource(R.string.cmd_totp))
                CodeBlock(command = stringResource(R.string.cmd_totp_rotate))
                Spacer(Modifier.height(4.dp))
                PrimaryButton(
                    text = stringResource(R.string.totp_reset_btn),
                    leadingIcon = Icons.Rounded.Key,
                ) {
                    showTotpSheet = false
                    showTotpSetup = true
                }
            }
        }
    }

    // Xiaomi/HyperOS keep-alive bottom sheet
    if (showBatterySheet) {
        ModalBottomSheet(
            onDismissRequest = { showBatterySheet = false },
            sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
            containerColor = c.surfaceContainerLow,
            scrimColor = c.scrim,
            shape = TurboRadii.extraLargeTop,
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp)
                    .padding(bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Text(
                    text = stringResource(R.string.set_battery),
                    style = MaterialTheme.typography.titleLarge,
                    color = c.onSurface,
                )
                Text(
                    text = stringResource(R.string.set_battery_d),
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.onSurfaceVariant,
                )
                PrimaryButton(
                    text = stringResource(R.string.set_battery_open),
                    leadingIcon = Icons.Rounded.BatterySaver,
                ) {
                    showBatterySheet = false
                    BatteryGuide.available(ctx).firstOrNull()?.let { BatteryGuide.open(ctx, it) }
                }
            }
        }
    }

    val totpStateLabel = when {
        !totpOn -> stringResource(R.string.val_off)
        enrollPending -> stringResource(R.string.totp_state_pending)
        else -> stringResource(R.string.totp_state_ready)
    }
    val totpStateColor = when {
        !totpOn -> c.onSurfaceVariant
        enrollPending -> c.warn
        else -> c.primary
    }

    val presetDisplay = stringResource(
        when (presetName) {
            "balanced" -> R.string.preset_balanced
            "strict" -> R.string.preset_strict
            else -> R.string.preset_easy
        }
    )

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = TurboSpacing.gutter),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text(
            text = stringResource(R.string.set_title),
            style = MaterialTheme.typography.headlineSmall,
            color = c.onSurface,
            modifier = Modifier.padding(top = 4.dp),
        )

        // Group 1 (v3 Screen 16): Security · set on the PC
        Text(
            text = stringResource(R.string.set_g_security),
            style = MaterialTheme.typography.labelLarge,
            color = c.onSurfaceVariant,
            modifier = Modifier.padding(top = 2.dp),
        )

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clip(TurboRadii.large)
                .background(c.surfaceContainerHigh)
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Icon(
                imageVector = Icons.Rounded.Shield,
                contentDescription = null,
                tint = c.onPrimaryContainer,
                modifier = Modifier
                    .padding(top = 1.dp)
                    .size(22.dp),
            )
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    text = stringResource(R.string.set_level, presetDisplay),
                    style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold),
                    color = c.onSurface,
                    modifier = Modifier.testTag("level"),
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    text = stringResource(R.string.set_pc_short),
                    style = MaterialTheme.typography.bodySmall,
                    color = c.onSurfaceVariant,
                )
            }
        }

        val strAlwaysOn = stringResource(R.string.val_always_on)
        val strOn = stringResource(R.string.val_on)
        val strOff = stringResource(R.string.val_off)

        GroupedListCard {
            SettingsListRow(
                icon = Icons.Rounded.Videocam,
                title = stringResource(R.string.set_row_screen_view),
                subtitle = stringResource(R.string.set_row_screen_view_d),
                valueText = if (screenViewOn) {
                    stringResource(R.string.val_on_fps, formatFps(screenViewFps))
                } else {
                    strOff
                },
                valueColor = if (screenViewOn) c.primary else c.onSurfaceVariant,
                showChevron = screenViewOn,
                onClick = if (screenViewOn) ({ showFpsSheet = true }) else null,
                modifier = Modifier.testTag("row_screen_view"),
            )
            InsetDivider()
            SettingsListRow(
                icon = Icons.Rounded.Mouse,
                title = stringResource(R.string.set_row_lock_v3),
                valueText = stringResource(
                    if (effectiveLockMode == "whole_task") R.string.set_lock_task_v3 else R.string.set_lock_real
                ),
                valueColor = if (effectiveLockMode == "whole_task") c.primary else c.onSurfaceVariant,
                modifier = Modifier.testTag("row_lock"),
            )
            InsetDivider()
            SettingsListRow(
                icon = Icons.Rounded.GppMaybe,
                title = stringResource(R.string.set_row_ask),
                valueText = if (askOn) strOn else strOff,
                valueColor = if (askOn) c.primary else c.onSurfaceVariant,
                modifier = Modifier.testTag("row_ask"),
            )
            InsetDivider()
            SettingsListRow(
                icon = Icons.Rounded.Lock,
                title = stringResource(R.string.set_row_floor),
                subtitle = stringResource(R.string.set_row_floor_d),
                valueText = strAlwaysOn,
                valueColor = c.onSurfaceVariant,
                modifier = Modifier.testTag("row_floor"),
            )
            InsetDivider()
            SettingsListRow(
                icon = Icons.Rounded.DesktopWindows,
                title = stringResource(R.string.set_row_border),
                valueText = if (borderOn) strAlwaysOn else strOff,
                valueColor = c.onSurfaceVariant,
                modifier = Modifier.testTag("row_border"),
            )
            InsetDivider()
            SettingsListRow(
                icon = Icons.Rounded.Password,
                title = stringResource(R.string.set_row_totp_v2),
                valueText = if (totpOn) strOn else strOff,
                valueColor = if (totpOn) c.primary else c.onSurfaceVariant,
                modifier = Modifier.testTag("row_totp"),
            )
            InsetDivider()
            SettingsListRow(
                icon = Icons.Rounded.Fingerprint,
                title = stringResource(R.string.set_row_bio),
                valueText = if (bioOn) strOn else strOff,
                valueColor = if (bioOn) c.primary else c.onSurfaceVariant,
                modifier = Modifier.testTag("row_bio"),
            )
            InsetDivider()
            SettingsListRow(
                icon = Icons.Rounded.Cloud,
                title = stringResource(R.string.set_row_cf),
                valueText = if (cfOn) strOn else strOff,
                valueColor = if (cfOn) c.primary else c.onSurfaceVariant,
                modifier = Modifier.testTag("row_cf"),
            )
        }

        // Group 2: On this phone
        Spacer(Modifier.height(6.dp))
        Text(
            text = stringResource(R.string.set_g_phone),
            style = MaterialTheme.typography.labelLarge,
            color = c.onSurfaceVariant,
        )
        GroupedListCard {
            SettingsListRow(
                icon = Icons.Rounded.Language,
                title = stringResource(R.string.set_lang_row),
                valueText = currentLangLabel,
                showChevron = true,
                onClick = { showLangSheet = true },
            )
            InsetDivider()
            SettingsListRow(
                icon = Icons.Rounded.Key,
                title = stringResource(R.string.set_2fa_row),
                valueText = totpStateLabel,
                valueColor = totpStateColor,
                showChevron = true,
                onClick = { showTotpSheet = true },
            )
            InsetDivider()
            SettingsToggleRow(
                icon = Icons.Rounded.Tune,
                title = stringResource(R.string.set_cost_toggle),
                subtitle = stringResource(
                    if (showApiCost) R.string.set_cost_sub_on else R.string.set_cost_sub_off
                ),
                checked = showApiCost,
                onCheckedChange = { Graph.setShowApiCost(it) },
                modifier = Modifier.testTag("costToggle"),
            )
            InsetDivider()
            SettingsListRow(
                icon = Icons.Rounded.BatterySaver,
                title = stringResource(R.string.set_battery),
                showChevron = true,
                modifier = Modifier.testTag("battery"),
                onClick = { showBatterySheet = true },
            )
        }

        // Group 3: Connection
        Spacer(Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.set_conn),
            style = MaterialTheme.typography.labelLarge,
            color = c.onSurfaceVariant,
        )
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(TurboRadii.large)
                .background(c.surfaceContainer)
                .padding(TurboSpacing.cardPadding),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            val configuredUrls = try { Graph.prefs.urls } catch (_: Exception) { emptyList() }
            configuredUrls.forEach { (n, u) ->
                Text(
                    text = "$n: $u",
                    style = TurboType.monoCode,
                    color = c.onSurfaceVariant,
                )
            }
            TurboTextField(
                value = url,
                onValueChange = { url = it },
                hint = stringResource(R.string.set_url_hint),
                keyboardType = KeyboardType.Uri,
                tag = "addUrl",
            )
            GhostButton(
                text = stringResource(R.string.set_url_add),
                modifier = Modifier.testTag("addUrlButton"),
            ) {
                val trimmed = url.trim()
                if (trimmed.isNotEmpty()) {
                    Graph.prefs.setUrl(Protocol.transportName(trimmed), trimmed)
                    url = ""
                }
            }
            if (needAccessLogin) {
                PrimaryButton(
                    text = stringResource(R.string.set_access_login),
                    color = c.warn,
                    fg = c.onWarn,
                ) { showCf = true }
            } else {
                GhostButton(
                    text = stringResource(R.string.set_access_login),
                ) { showCf = true }
            }
        }

        // Group 4: Wake PC
        Spacer(Modifier.height(8.dp))
        Text(
            text = stringResource(R.string.set_wake),
            style = MaterialTheme.typography.labelLarge,
            color = c.onSurfaceVariant,
        )
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(TurboRadii.large)
                .background(c.surfaceContainer)
                .padding(TurboSpacing.cardPadding),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            TurboTextField(
                value = relayUrl,
                onValueChange = { relayUrl = it },
                hint = stringResource(R.string.set_wake_relay),
                keyboardType = KeyboardType.Uri,
                tag = "relayUrl",
            )
            TurboTextField(
                value = relayCode,
                onValueChange = { relayCode = it },
                hint = stringResource(R.string.set_wake_pair),
                keyboardType = KeyboardType.Number,
            )
            GhostButton(text = stringResource(R.string.set_wake_pair)) {
                scope.launch {
                    try {
                        Graph.relay.pair(relayUrl, relayCode, "phone")
                    } catch (e: Exception) {
                        Graph.fail(e)
                    }
                }
            }
            TonalButton(
                text = stringResource(R.string.set_wake_button),
                modifier = Modifier.testTag("wake"),
            ) {
                Graph.prefs.relayUrl = relayUrl
                scope.launch { Graph.wakePc() }
            }
            if (wake.isNotBlank()) {
                Text(
                    text = wake,
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.warn,
                    modifier = Modifier.testTag("wakeState"),
                )
            }
        }

        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = {
                scope.launch {
                    Graph.unpairRemote()
                    onUnpair()
                }
            },
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = TurboSpacing.buttonSecondary)
                .testTag("unpair"),
            shape = TurboRadii.full,
            border = BorderStroke(1.dp, c.outline),
            colors = ButtonDefaults.outlinedButtonColors(contentColor = c.stopText),
        ) {
            Icon(
                imageVector = Icons.Rounded.LinkOff,
                contentDescription = null,
                modifier = Modifier.size(20.dp),
            )
            Spacer(Modifier.width(8.dp))
            Text(text = stringResource(R.string.set_unpair), style = TurboType.button)
        }
        Spacer(Modifier.height(16.dp))
    }
}

/** Cloudflare Access: log in inside a WebView once, keep the CF_Authorization cookie for the app's requests. */
@Composable
fun CfLogin(onDone: () -> Unit) {
    val c = LocalTurboColors.current
    val target = try { Graph.prefs.urls.firstOrNull { it.first == "cloudflare" }?.second } catch (_: Exception) { null }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding(),
    ) {
        if (target != null) {
            AndroidView(
                factory = { ctx -> WebView(ctx).apply { settings.javaScriptEnabled = true; loadUrl(target) } },
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
            )
        } else {
            Text(
                text = stringResource(R.string.set_url_hint),
                style = MaterialTheme.typography.bodyLarge,
                color = c.onSurfaceVariant,
                modifier = Modifier
                    .weight(1f)
                    .padding(TurboSpacing.gutter),
            )
        }
        PrimaryButton(
            text = stringResource(R.string.btn_ok),
            modifier = Modifier
                .padding(TurboSpacing.gutter)
                .testTag("cfDone"),
        ) {
            target?.let { u ->
                CookieManager.getInstance().getCookie(u)
                    ?.split(";")
                    ?.map { it.trim() }
                    ?.firstOrNull { it.startsWith("CF_Authorization=") }
                    ?.let { Graph.prefs.cfCookie = it.removePrefix("CF_Authorization=") }
            }
            onDone()
        }
    }
}
