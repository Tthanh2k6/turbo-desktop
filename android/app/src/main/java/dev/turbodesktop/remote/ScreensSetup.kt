package dev.turbodesktop.remote

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.Help
import androidx.compose.material.icons.automirrored.rounded.OpenInNew
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Cloud
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.ContentPaste
import androidx.compose.material.icons.rounded.DesktopWindows
import androidx.compose.material.icons.rounded.Fingerprint
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Keyboard
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.LockOpen
import androidx.compose.material.icons.rounded.QrCodeScanner
import androidx.compose.material.icons.rounded.RadioButtonChecked
import androidx.compose.material.icons.rounded.RadioButtonUnchecked
import androidx.compose.material.icons.rounded.Refresh
import androidx.compose.material.icons.rounded.Schedule
import androidx.compose.material.icons.rounded.Timer
import androidx.compose.material.icons.rounded.TimerOff
import androidx.compose.material.icons.rounded.VerifiedUser
import androidx.compose.material.icons.rounded.Visibility
import androidx.compose.material.icons.rounded.VisibilityOff
import androidx.compose.material.icons.rounded.Wifi
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import kotlinx.coroutines.launch

private data class PresetSpec(
    val code: String,
    val nameRes: Int,
    val tagRes: Int,
    val facts: List<Pair<ImageVector, Int>>,
)

@Composable
fun Welcome(onDone: () -> Unit) {
    val c = LocalTurboColors.current
    var sel by remember { mutableIntStateOf(0) }
    val presets = remember {
        listOf(
            PresetSpec(
                code = "easy",
                nameRes = R.string.preset_easy,
                tagRes = R.string.preset_easy_tag,
                facts = listOf(
                    Icons.Rounded.Wifi to R.string.preset_easy_f1,
                    Icons.Rounded.Schedule to R.string.preset_easy_f2,
                    Icons.Rounded.VerifiedUser to R.string.preset_easy_f3,
                ),
            ),
            PresetSpec(
                code = "balanced",
                nameRes = R.string.preset_balanced,
                tagRes = R.string.preset_balanced_tag,
                facts = listOf(
                    Icons.Rounded.Wifi to R.string.preset_bal_f1,
                    Icons.Rounded.Schedule to R.string.preset_bal_f2,
                    Icons.Rounded.VerifiedUser to R.string.preset_bal_f3,
                ),
            ),
            PresetSpec(
                code = "strict",
                nameRes = R.string.preset_strict,
                tagRes = R.string.preset_strict_tag,
                facts = listOf(
                    Icons.Rounded.Fingerprint to R.string.preset_str_f1,
                    Icons.Rounded.VerifiedUser to R.string.preset_str_f2,
                    Icons.Rounded.Cloud to R.string.preset_str_f3,
                ),
            ),
        )
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .navigationBarsPadding()
            .imePadding(),   // keep fields and buttons above the keyboard
    ) {
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .statusBarsPadding()
                .padding(horizontal = TurboSpacing.gutter),
        ) {
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(32.dp)
                        .clip(RoundedCornerShape(10.dp))
                        .background(c.primaryContainer),
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = Icons.Rounded.DesktopWindows,
                        contentDescription = null,
                        tint = c.onPrimaryContainer,
                        modifier = Modifier.size(18.dp),
                    )
                }
                Spacer(Modifier.width(10.dp))
                Text(
                    text = stringResource(R.string.app_name),
                    style = MaterialTheme.typography.titleMedium,
                    color = c.onSurface,
                )
            }
            Spacer(Modifier.height(16.dp))
            Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                Text(
                    text = stringResource(R.string.step_of, 1, 3),
                    style = MaterialTheme.typography.labelMedium,
                    color = c.onSurfaceVariant,
                )
                Spacer(Modifier.width(12.dp))
                Row(
                    modifier = Modifier.weight(1f),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    for (i in 0 until 3) {
                        Box(
                            Modifier
                                .weight(1f)
                                .height(4.dp)
                                .clip(RoundedCornerShape(2.dp))
                                .background(if (i == 0) c.primary else c.surfaceContainerHighest)
                        )
                    }
                }
            }
            Spacer(Modifier.height(16.dp))
            Text(
                text = stringResource(R.string.wel_title),
                style = MaterialTheme.typography.headlineMedium,
                color = c.onSurface,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = stringResource(R.string.wel_sub),
                style = MaterialTheme.typography.bodyLarge,
                color = c.onSurfaceVariant,
            )
            Spacer(Modifier.height(16.dp))

            presets.forEachIndexed { index, spec ->
                val selected = sel == index
                val shape = TurboRadii.largeIncreased
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("preset$index")
                        .clip(shape)
                        .background(if (selected) c.surfaceContainerHigh else c.surfaceContainer)
                        .then(if (selected) Modifier.border(2.dp, c.primary, shape) else Modifier)
                        .selectable(
                            selected = selected,
                            role = Role.RadioButton,
                            onClick = { sel = index },
                        )
                        .padding(16.dp),
                ) {
                    Row(verticalAlignment = if (selected) Alignment.Top else Alignment.CenterVertically) {
                        Icon(
                            imageVector = if (selected) Icons.Rounded.RadioButtonChecked else Icons.Rounded.RadioButtonUnchecked,
                            contentDescription = null,
                            tint = if (selected) c.primary else c.onSurfaceVariant,
                            modifier = Modifier
                                .padding(top = if (selected) 2.dp else 0.dp)
                                .size(24.dp),
                        )
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(
                                text = stringResource(spec.nameRes),
                                style = if (selected) MaterialTheme.typography.titleLarge else MaterialTheme.typography.titleMedium,
                                color = c.onSurface,
                            )
                            Spacer(Modifier.height(if (selected) 6.dp else 2.dp))
                            if (selected) {
                                Box(
                                    modifier = Modifier
                                        .clip(TurboRadii.full)
                                        .background(c.primaryContainer)
                                        .padding(horizontal = 10.dp, vertical = 4.dp),
                                ) {
                                    Text(
                                        text = stringResource(spec.tagRes),
                                        style = MaterialTheme.typography.labelMedium,
                                        color = c.onPrimaryContainer,
                                    )
                                }
                                Spacer(Modifier.height(12.dp))
                                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    spec.facts.forEach { (ic, textRes) ->
                                        Row(verticalAlignment = Alignment.Top) {
                                            Icon(
                                                imageVector = ic,
                                                contentDescription = null,
                                                tint = c.onSurfaceVariant,
                                                modifier = Modifier
                                                    .padding(top = 1.dp)
                                                    .size(18.dp),
                                            )
                                            Spacer(Modifier.width(10.dp))
                                            Text(
                                                text = stringResource(textRes),
                                                style = MaterialTheme.typography.bodyMedium,
                                                color = c.onSurface,
                                            )
                                        }
                                    }
                                }
                            } else {
                                Text(
                                    text = stringResource(spec.tagRes),
                                    style = MaterialTheme.typography.bodySmall,
                                    color = c.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
                Spacer(Modifier.height(10.dp))
            }

            Text(
                text = stringResource(R.string.wel_pc_preset_wins),
                style = MaterialTheme.typography.bodySmall,
                color = c.onSurfaceVariant,
                modifier = Modifier
                    .padding(top = 2.dp)
                    .testTag("welcomePcPresetNote"),
            )
            Text(
                text = stringResource(R.string.wel_foot),
                style = MaterialTheme.typography.bodySmall,
                color = c.muted,
                modifier = Modifier.padding(top = 4.dp, bottom = 12.dp),
            )
        }

        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(c.bg)
                .padding(horizontal = TurboSpacing.gutter, vertical = 12.dp),
        ) {
            PrimaryButton(
                text = stringResource(R.string.preset_use, stringResource(presets[sel].nameRes)),
                modifier = Modifier.testTag("usePreset"),
            ) {
                Graph.prefs.preset = presets[sel].code
                onDone()
            }
        }
    }
}

@androidx.annotation.OptIn(ExperimentalGetImage::class)
@Composable
fun QrScanner(modifier: Modifier, onText: (String) -> Unit) {
    val ctx = LocalContext.current
    val owner = LocalLifecycleOwner.current
    AndroidView(
        modifier = modifier,
        factory = { c ->
            PreviewView(c).also { pv ->
                val fut = ProcessCameraProvider.getInstance(c)
                fut.addListener({
                    val provider = fut.get()
                    val preview = Preview.Builder().build().also { it.setSurfaceProvider(pv.surfaceProvider) }
                    val scanner = BarcodeScanning.getClient(
                        BarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()
                    )
                    val analysis = ImageAnalysis.Builder()
                        .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                        .build()
                        .also { a ->
                            a.setAnalyzer(ContextCompat.getMainExecutor(c)) { proxy ->
                                val media = proxy.image
                                if (media == null) {
                                    proxy.close()
                                } else {
                                    scanner.process(InputImage.fromMediaImage(media, proxy.imageInfo.rotationDegrees))
                                        .addOnSuccessListener { codes -> codes.firstOrNull()?.rawValue?.let(onText) }
                                        .addOnCompleteListener { proxy.close() }
                                }
                            }
                        }
                    try {
                        provider.unbindAll()
                        provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis)
                    } catch (_: Exception) {
                    }
                }, ContextCompat.getMainExecutor(ctx))
            }
        },
    )
}

@Composable
private fun StepBadgeRow(number: Int, text: String) {
    val c = LocalTurboColors.current
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(24.dp)
                .clip(TurboRadii.full)
                .background(c.surfaceContainerHighest),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = number.toString(),
                style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold),
                color = c.onSurface,
            )
        }
        Spacer(Modifier.width(10.dp))
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            color = c.onSurface,
        )
    }
}

@Composable
fun PairScreen(
    activity: FragmentActivity,
    onBack: (() -> Unit)? = null,
    onPaired: () -> Unit,
) {
    val c = LocalTurboColors.current
    val scope = rememberCoroutineScope()
    var camOk by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(activity, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
        )
    }
    var manualOpen by remember { mutableStateOf(!camOk) }
    val askCam = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        camOk = granted
        if (!granted) manualOpen = true
    }
    LaunchedEffect(Unit) {
        if (!camOk) askCam.launch(Manifest.permission.CAMERA)
    }

    var paste by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var url by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val status by Graph.status.collectAsState()

    fun doPair(text: String?) {
        scope.launch {
            if (busy) return@launch
            busy = true
            if (Biometric.authenticate(activity) &&
                Graph.pair(text, url.ifBlank { null }, code.ifBlank { null })
            ) {
                onPaired()
            }
            busy = false
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .navigationBarsPadding()
            .imePadding(),   // keep fields and buttons above the keyboard
    ) {
        StepperHeader(step = 2, total = 3, onBack = onBack)
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = TurboSpacing.gutter),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column {
                Text(
                    text = stringResource(R.string.pair_title),
                    style = MaterialTheme.typography.headlineSmall,
                    color = c.onSurface,
                )
                Spacer(Modifier.height(2.dp))
                Text(
                    text = stringResource(R.string.pair_sub),
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.onSurfaceVariant,
                )
            }

            StepBadgeRow(1, stringResource(R.string.pair_run))
            CodeBlock(command = stringResource(R.string.cmd_pair))

            StepBadgeRow(2, stringResource(R.string.pair_scan))

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .then(if (camOk) Modifier.height(268.dp) else Modifier.heightIn(min = 200.dp))
                    .clip(TurboRadii.largeIncreased)
                    .background(c.viewfinderBg),
                contentAlignment = Alignment.Center,
            ) {
                if (camOk) {
                    QrScanner(Modifier.fillMaxSize()) { t ->
                        if (t.startsWith("turbo-pair:") && !busy) doPair(t)
                    }
                    val cornerColor = c.primary
                    Canvas(Modifier.size(160.dp)) {
                        val arm = 26.dp.toPx()
                        val stroke = Stroke(width = 4.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round)
                        val w = size.width
                        val h = size.height
                        val path = Path().apply {
                            moveTo(0f, arm); lineTo(0f, 0f); lineTo(arm, 0f)
                            moveTo(w - arm, 0f); lineTo(w, 0f); lineTo(w, arm)
                            moveTo(0f, h - arm); lineTo(0f, h); lineTo(arm, h)
                            moveTo(w - arm, h); lineTo(w, h); lineTo(w, h - arm)
                        }
                        drawPath(path, color = cornerColor, style = stroke)
                    }
                    Row(
                        modifier = Modifier
                            .align(Alignment.BottomCenter)
                            .padding(14.dp)
                            .clip(TurboRadii.full)
                            .background(c.playerPillBg)
                            .padding(horizontal = 16.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.QrCodeScanner,
                            contentDescription = null,
                            tint = c.onSurface,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = stringResource(R.string.pair_scanning),
                            style = MaterialTheme.typography.labelLarge,
                            color = c.onSurface,
                        )
                    }
                } else {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Text(
                            text = stringResource(R.string.pair_camera_off),
                            style = MaterialTheme.typography.bodyMedium,
                            color = c.onSurfaceVariant,
                        )
                        GhostButton(
                            text = stringResource(R.string.pair_allow_cam),
                            onClick = { askCam.launch(Manifest.permission.CAMERA) },
                        )
                    }
                }
            }

            Row(verticalAlignment = Alignment.Top) {
                Icon(
                    imageVector = Icons.Rounded.Info,
                    contentDescription = null,
                    tint = c.onSurfaceVariant,
                    modifier = Modifier
                        .padding(top = 1.dp)
                        .size(20.dp),
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    text = stringResource(R.string.pair_fp_note),
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.onSurfaceVariant,
                )
            }

            if (status.isNotBlank()) {
                Text(
                    text = status,
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.warn,
                    modifier = Modifier.testTag("status"),
                )
            }

            GhostButton(
                text = stringResource(R.string.pair_manual),
                leadingIcon = Icons.Rounded.Keyboard,
                onClick = { manualOpen = !manualOpen },
            )

            if (manualOpen) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(TurboRadii.large)
                        .background(c.surfaceContainer)
                        .padding(TurboSpacing.cardPadding),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    TurboTextField(
                        value = paste,
                        onValueChange = { paste = it },
                        hint = stringResource(R.string.pair_paste),
                        singleLine = false,
                        tag = "pairPaste",
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        TurboTextField(
                            value = code,
                            onValueChange = { code = it },
                            hint = stringResource(R.string.pair_code),
                            modifier = Modifier.weight(1f),
                            keyboardType = KeyboardType.Number,
                            tag = "pairCode",
                        )
                        TurboTextField(
                            value = url,
                            onValueChange = { url = it },
                            hint = stringResource(R.string.pair_url),
                            modifier = Modifier.weight(1f),
                            keyboardType = KeyboardType.Uri,
                            tag = "pairUrl",
                        )
                    }
                    PrimaryButton(
                        text = stringResource(R.string.pair_button),
                        modifier = Modifier.testTag("pairButton"),
                        enabled = !busy,
                    ) {
                        doPair(paste.ifBlank { null })
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TotpSetupScreen(
    activity: FragmentActivity,
    fromSettings: Boolean = false,
    onBack: (() -> Unit)? = null,
    onDone: () -> Unit,
) {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    var loading by remember { mutableStateOf(true) }
    var enroll by remember { mutableStateOf<TotpEnroll?>(null) }
    var keyRevealed by remember { mutableStateOf(false) } // 2FA key MUST start hidden
    var localFeedback by remember { mutableStateOf("") }
    val status by Graph.status.collectAsState()

    suspend fun loadKey(forcePrompt: Boolean) {
        loading = true
        localFeedback = ""
        if (forcePrompt) {
            if (!Biometric.authenticate(activity)) {
                loading = false
                return
            }
            enroll = Graph.fetchTotpEnrollment()
        } else {
            val first = Graph.fetchTotpEnrollment()
            if (first != null) {
                enroll = first
            } else if (Graph.totpEnrollPending.value) {
                // Auth key's 30 s window had expired before any HTTP 200/403 response
                Graph.status.value = ""
                if (Biometric.authenticate(activity)) {
                    enroll = Graph.fetchTotpEnrollment()
                }
            }
        }
        loading = false
    }

    LaunchedEffect(Unit) {
        loadKey(forcePrompt = fromSettings)
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .navigationBarsPadding()
            .imePadding(),   // keep fields and buttons above the keyboard
    ) {
        if (fromSettings) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .statusBarsPadding()
                    .padding(horizontal = 4.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(
                    onClick = { onBack?.invoke() ?: onDone() },
                    modifier = Modifier.size(TurboSpacing.touchMin),
                ) {
                    Icon(
                        imageVector = Icons.AutoMirrored.Rounded.ArrowBack,
                        contentDescription = stringResource(R.string.cd_back),
                        tint = c.onSurface,
                    )
                }
            }
        } else {
            StepperHeader(step = 3, total = 3, onBack = onBack)
        }

        if (loading) {
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(color = c.primary)
                    Spacer(Modifier.height(16.dp))
                    Text(
                        text = stringResource(R.string.totp_loading),
                        style = MaterialTheme.typography.bodyMedium,
                        color = c.onSurfaceVariant,
                    )
                }
            }
        } else {
            val activeEnroll = enroll
            if (activeEnroll != null) {
                // 03a: 2FA setup with secret key (starts hidden)
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = TurboSpacing.gutter),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    if (!fromSettings) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Rounded.CheckCircle,
                                contentDescription = null,
                                tint = c.primary,
                                modifier = Modifier.size(20.dp),
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = stringResource(R.string.totp_paired_with, pcDisplayName(ctx)),
                                style = MaterialTheme.typography.labelLarge,
                                color = c.primary,
                            )
                        }
                    }

                    Column {
                        Text(
                            text = stringResource(R.string.totp_setup_title),
                            style = MaterialTheme.typography.headlineSmall,
                            color = c.onSurface,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = stringResource(R.string.totp_setup_sub),
                            style = MaterialTheme.typography.bodyMedium,
                            color = c.onSurfaceVariant,
                        )
                    }

                    // Secret key card
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(TurboRadii.large)
                            .background(c.surfaceContainer)
                            .padding(TurboSpacing.cardPadding),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = stringResource(R.string.totp_secret_label),
                                style = MaterialTheme.typography.labelLarge,
                                color = c.onSurfaceVariant,
                                modifier = Modifier.weight(1f),
                            )
                            Row(
                                modifier = Modifier
                                    .defaultMinSize(minHeight = TurboSpacing.touchMin)
                                    .clip(TurboRadii.full)
                                    .background(c.surfaceContainerHigh)
                                    .clickable(role = Role.Button) { keyRevealed = !keyRevealed }
                                    .padding(horizontal = 14.dp, vertical = 8.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Icon(
                                    imageVector = if (keyRevealed) Icons.Rounded.VisibilityOff else Icons.Rounded.Visibility,
                                    contentDescription = null,
                                    tint = c.onSurface,
                                    modifier = Modifier.size(18.dp),
                                )
                                Spacer(Modifier.width(6.dp))
                                Text(
                                    text = stringResource(if (keyRevealed) R.string.totp_hide else R.string.totp_show),
                                    style = MaterialTheme.typography.labelLarge,
                                    color = c.onSurface,
                                )
                            }
                        }
                        Spacer(Modifier.height(10.dp))
                        val groups = remember(activeEnroll.secret) {
                            activeEnroll.secret.uppercase().chunked(4)
                        }
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(14.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                            maxItemsInEachRow = 4,
                        ) {
                            groups.forEach { g ->
                                Text(
                                    text = if (keyRevealed) g else "•".repeat(g.length),
                                    style = TurboType.monoKey,
                                    color = c.onSurface,
                                )
                            }
                        }
                        Spacer(Modifier.height(12.dp))
                        Text(
                            text = stringResource(R.string.totp_meta_fmt, activeEnroll.issuer, activeEnroll.account),
                            style = MaterialTheme.typography.bodySmall,
                            color = c.muted,
                        )
                    }

                    PrimaryButton(
                        text = stringResource(R.string.totp_open_auth),
                        trailingIcon = Icons.AutoMirrored.Rounded.OpenInNew,
                    ) {
                        if (!openInAuthenticator(ctx, activeEnroll.otpauth)) {
                            localFeedback = ctx.getString(R.string.totp_no_auth_app)
                        }
                    }

                    val secretLabel = stringResource(R.string.totp_secret_label)
                    val copiedText = stringResource(R.string.totp_key_copied)
                    GhostButton(
                        text = stringResource(R.string.totp_copy_key),
                        leadingIcon = Icons.Rounded.ContentCopy,
                    ) {
                        copySensitive(ctx, secretLabel, activeEnroll.secret)
                        localFeedback = copiedText
                    }

                    if (localFeedback.isNotBlank()) {
                        Text(
                            text = localFeedback,
                            style = MaterialTheme.typography.bodySmall,
                            color = c.primary,
                        )
                    }

                    Row(verticalAlignment = Alignment.Top) {
                        Icon(
                            imageVector = Icons.Rounded.Timer,
                            contentDescription = null,
                            tint = c.onSurfaceVariant,
                            modifier = Modifier
                                .padding(top = 1.dp)
                                .size(18.dp),
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(
                            text = stringResource(R.string.totp_one_shot_note),
                            style = MaterialTheme.typography.bodySmall,
                            color = c.onSurfaceVariant,
                        )
                    }

                    HorizontalDivider(color = c.outlineVariant)

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Rounded.Help,
                            contentDescription = null,
                            tint = c.onSurfaceVariant,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(
                            text = stringResource(R.string.totp_lost_help),
                            style = MaterialTheme.typography.bodySmall,
                            color = c.onSurfaceVariant,
                        )
                    }
                    CodeBlock(
                        command = stringResource(R.string.cmd_totp_rotate),
                        textColor = c.onSurface,
                    )
                    Spacer(Modifier.height(8.dp))
                }

                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(c.bg)
                        .padding(horizontal = TurboSpacing.gutter, vertical = 12.dp),
                ) {
                    TonalButton(
                        text = stringResource(R.string.totp_done),
                        onClick = onDone,
                    )
                }
            } else {
                // 03b: Key enrollment window expired
                Column(
                    modifier = Modifier
                        .weight(1f)
                        .verticalScroll(rememberScrollState())
                        .padding(horizontal = TurboSpacing.gutter),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Spacer(Modifier.height(4.dp))
                    Box(
                        modifier = Modifier
                            .size(72.dp)
                            .clip(TurboRadii.full)
                            .background(c.warnContainer),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.TimerOff,
                            contentDescription = null,
                            tint = c.onWarnContainer,
                            modifier = Modifier.size(36.dp),
                        )
                    }

                    Column {
                        Text(
                            text = stringResource(R.string.totp_exp_title),
                            style = MaterialTheme.typography.headlineSmall,
                            color = c.onSurface,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(
                            text = stringResource(R.string.totp_exp_sub),
                            style = MaterialTheme.typography.bodyMedium,
                            color = c.onSurfaceVariant,
                        )
                    }

                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(TurboRadii.large)
                            .background(c.surfaceContainer)
                            .padding(TurboSpacing.cardPadding),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        StepBadgeRow(1, stringResource(R.string.pair_run))
                        CodeBlock(command = stringResource(R.string.cmd_totp))
                        StepBadgeRow(2, stringResource(R.string.totp_exp_step2))
                    }

                    Row(verticalAlignment = Alignment.Top) {
                        Icon(
                            imageVector = Icons.Rounded.QrCodeScanner,
                            contentDescription = null,
                            tint = c.onSurfaceVariant,
                            modifier = Modifier
                                .padding(top = 1.dp)
                                .size(18.dp),
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(
                            text = stringResource(R.string.totp_exp_qr_note),
                            style = MaterialTheme.typography.bodySmall,
                            color = c.onSurfaceVariant,
                        )
                    }

                    Row(verticalAlignment = Alignment.Top) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Rounded.Help,
                            contentDescription = null,
                            tint = c.onSurfaceVariant,
                            modifier = Modifier
                                .padding(top = 1.dp)
                                .size(18.dp),
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(
                            text = stringResource(R.string.totp_exp_rotate_note),
                            style = MaterialTheme.typography.bodySmall,
                            color = c.onSurfaceVariant,
                        )
                    }

                    if (status.isNotBlank() && status != stringResource(R.string.st_enroll_closed)) {
                        Text(
                            text = status,
                            style = MaterialTheme.typography.bodySmall,
                            color = c.warn,
                            modifier = Modifier.testTag("status"),
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                }

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(c.bg)
                        .padding(horizontal = TurboSpacing.gutter, vertical = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    PrimaryButton(
                        text = stringResource(R.string.totp_retry),
                        leadingIcon = Icons.Rounded.Refresh,
                    ) {
                        scope.launch { loadKey(forcePrompt = true) }
                    }
                    TextActionButton(
                        text = stringResource(R.string.totp_added_on_pc),
                        fg = c.primary,
                        onClick = onDone,
                    )
                }
            }
        }
    }
}

@Composable
fun OpenSession(activity: FragmentActivity, onUnpair: () -> Unit) {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val needs by Graph.needs.collectAsState()
    val policy by Graph.policy.collectAsState()
    val status by Graph.status.collectAsState()
    var code by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        Graph.refreshPolicy()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .navigationBarsPadding()
            .imePadding(),   // keep fields and buttons above the keyboard
    ) {
        SessionTopHeader()
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = TurboSpacing.gutter),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Spacer(Modifier.height(4.dp))
            Column {
                Text(
                    text = stringResource(R.string.sess_title),
                    style = MaterialTheme.typography.headlineMedium,
                    color = c.onSurface,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = stringResource(R.string.sess_expired),
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.onSurfaceVariant,
                )
            }

            if (needs.totp) {
                // 04b: Session with 6-box TOTP input
                Spacer(Modifier.height(4.dp))
                Text(
                    text = stringResource(R.string.sess_code_label),
                    style = MaterialTheme.typography.labelLarge,
                    color = c.onSurface,
                )
                OtpSixBoxInput(
                    code = code,
                    onCodeChange = { code = it },
                )
                Text(
                    text = stringResource(R.string.sess_hint),
                    style = MaterialTheme.typography.bodySmall,
                    color = c.onSurfaceVariant,
                )
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton(
                        onClick = {
                            val pasted = readClipboardSixDigits(ctx)
                            if (pasted != null) {
                                code = pasted
                            } else {
                                Graph.status.value = ctx.getString(R.string.sess_paste_empty)
                            }
                        },
                        modifier = Modifier.heightIn(min = TurboSpacing.touchMin),
                        shape = TurboRadii.full,
                        border = BorderStroke(1.dp, c.outline),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = c.onSurface),
                        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 10.dp),
                    ) {
                        Icon(
                            imageVector = Icons.Rounded.ContentPaste,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(text = stringResource(R.string.sess_paste), style = MaterialTheme.typography.labelLarge)
                    }
                    OutlinedButton(
                        onClick = {
                            if (!launchAuthenticatorApp(ctx)) {
                                Graph.status.value = ctx.getString(R.string.totp_no_auth_app)
                            }
                        },
                        modifier = Modifier.heightIn(min = TurboSpacing.touchMin),
                        shape = TurboRadii.full,
                        border = BorderStroke(1.dp, c.outline),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = c.onSurface),
                        contentPadding = PaddingValues(horizontal = 16.dp, vertical = 10.dp),
                    ) {
                        Icon(
                            imageVector = Icons.AutoMirrored.Rounded.OpenInNew,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(text = stringResource(R.string.sess_open_auth), style = MaterialTheme.typography.labelLarge)
                    }
                }

                HorizontalDivider(color = c.outlineVariant, modifier = Modifier.padding(vertical = 4.dp))

                if (needs.biometric) {
                    Row(verticalAlignment = Alignment.Top) {
                        Icon(
                            imageVector = Icons.Rounded.Fingerprint,
                            contentDescription = null,
                            tint = c.onSurfaceVariant,
                            modifier = Modifier
                                .padding(top = 1.dp)
                                .size(18.dp),
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(
                            text = stringResource(R.string.sess_bio_note),
                            style = MaterialTheme.typography.bodySmall,
                            color = c.onSurfaceVariant,
                        )
                    }
                }
                Row(verticalAlignment = Alignment.Top) {
                    Icon(
                        imageVector = Icons.Rounded.Lock,
                        contentDescription = null,
                        tint = c.onSurfaceVariant,
                        modifier = Modifier
                            .padding(top = 1.dp)
                            .size(18.dp),
                    )
                    Spacer(Modifier.width(10.dp))
                    Text(
                        text = stringResource(R.string.sess_foot),
                        style = MaterialTheme.typography.bodySmall,
                        color = c.onSurfaceVariant,
                    )
                }
            } else {
                // 04a: Plain session (no 2FA required)
                val pCode = policy?.optString("preset")?.ifBlank { null }
                    ?: (try { Graph.prefs.preset } catch (_: Exception) { "" }).ifBlank { null }
                val hoursRaw = policy?.optDouble("sessionHours", 0.0) ?: 0.0
                val presetTitle = if (pCode != null && !hoursRaw.isNaN() && hoursRaw > 0.0) {
                    val pLabel = stringResource(
                        when (pCode) {
                            "balanced" -> R.string.preset_balanced
                            "strict" -> R.string.preset_strict
                            else -> R.string.preset_easy
                        }
                    )
                    val hStr = if (hoursRaw % 1.0 == 0.0) hoursRaw.toInt().toString() else "%.1f".format(hoursRaw)
                    stringResource(R.string.sess_preset_hours, pLabel, hStr)
                } else {
                    stringResource(R.string.sess_no_totp_title)
                }
                val presetSub = if (pCode != null && !hoursRaw.isNaN() && hoursRaw > 0.0) {
                    stringResource(R.string.sess_no_totp_title)
                } else {
                    stringResource(if (needs.biometric) R.string.sess_no_totp_sub_bio else R.string.sess_no_totp_sub_plain)
                }
                Spacer(Modifier.height(4.dp))
                GroupedListCard {
                    SettingsListRow(
                        icon = Icons.Rounded.QrCodeScanner,
                        title = stringResource(R.string.sess_info1),
                        subtitle = stringResource(R.string.sess_paired_sub, pcDisplayName(ctx)),
                    )
                    InsetDivider()
                    SettingsListRow(
                        icon = if (needs.biometric) Icons.Rounded.Fingerprint else Icons.Rounded.Schedule,
                        title = presetTitle,
                        subtitle = presetSub,
                    )
                }
            }

            if (status.isNotBlank()) {
                Text(
                    text = status,
                    style = MaterialTheme.typography.bodyMedium,
                    color = c.warn,
                    modifier = Modifier.testTag("status"),
                )
            }
            Spacer(Modifier.height(8.dp))
        }

        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(c.bg)
                .padding(horizontal = TurboSpacing.gutter, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            PrimaryButton(
                text = stringResource(
                    if (needs.totp || needs.biometric) R.string.sess_button else R.string.sess_button_plain
                ),
                leadingIcon = if (needs.biometric) Icons.Rounded.Fingerprint else Icons.Rounded.LockOpen,
                modifier = Modifier.testTag("openSession"),
                enabled = !busy,
            ) {
                scope.launch {
                    if (busy) return@launch
                    busy = true
                    runWithBiometricIfNeeded(activity, needs.biometric) {
                        Graph.openSession(if (needs.totp) code else "")
                    }
                    busy = false
                }
            }
            TextActionButton(
                text = stringResource(R.string.set_unpair),
                fg = c.stopText,
                modifier = Modifier.testTag("unpairSession"),
            ) {
                scope.launch {
                    Graph.unpairRemote()
                    onUnpair()
                }
            }
        }
    }
}
