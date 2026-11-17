package dev.turbodesktop.remote

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.webkit.CookieManager
import android.webkit.WebView
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** Colours from design/mockups/_generate.py (all text pairs checked for WCAG AA 4.5:1). */
object Pal {
    val BG = Color(0xFF14161A); val S1 = Color(0xFF1D2026); val S2 = Color(0xFF262A32); val LINE = Color(0xFF343944)
    val TX = Color(0xFFECE9E2); val TX2 = Color(0xFFA9ADB5); val TX3 = Color(0xFF9AA0AB)
    val MINT = Color(0xFF5CD6B0); val AMBER = Color(0xFFF2B84B); val RED = Color(0xFFFF6B63); val ORANGE = Color(0xFFE0461D)
    val ON_MINT = Color(0xFF08201A)
}

private val Shape16 = RoundedCornerShape(16.dp)
private val Shape24 = RoundedCornerShape(24.dp)

@Composable
fun TurboTheme(content: @Composable () -> Unit) = MaterialTheme(
    colorScheme = darkColorScheme(primary = Pal.MINT, onPrimary = Pal.ON_MINT, background = Pal.BG, surface = Pal.S1,
        onSurface = Pal.TX, onBackground = Pal.TX, error = Pal.RED)
) { Box(Modifier.fillMaxSize().background(Pal.BG), content = { content() }) }

enum class Tab(val label: Int, val glyph: String) {
    TASKS(R.string.tab_tasks, "▤"), LIVE(R.string.tab_live, "▶"), APPROVALS(R.string.tab_approvals, "✔"),
    AUDIT(R.string.tab_audit, "☰"), SETTINGS(R.string.tab_settings, "⚙")
}

private fun routeName(v: String) = v.replaceFirstChar { it.uppercase() }

// ============================================================================================ small pieces
@Composable
fun TCard(modifier: Modifier = Modifier, fill: Color = Pal.S1, stroke: Color? = null, content: @Composable () -> Unit) {
    Box(modifier.fillMaxWidth().clip(Shape16).background(fill).then(if (stroke != null) Modifier.border(1.5.dp, stroke, Shape16) else Modifier)
        .padding(16.dp)) { content() }
}

@Composable
fun PrimaryButton(text: String, modifier: Modifier = Modifier, color: Color = Pal.MINT, fg: Color = Pal.ON_MINT, onClick: () -> Unit) =
    Button(onClick, modifier.fillMaxWidth().heightIn(min = 52.dp), shape = Shape24,
        colors = ButtonDefaults.buttonColors(containerColor = color, contentColor = fg)) { Text(text, fontWeight = FontWeight.SemiBold, fontSize = 16.sp) }

@Composable
fun GhostButton(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) =
    OutlinedButton(onClick, modifier.fillMaxWidth().heightIn(min = 52.dp), shape = Shape24, border = BorderStroke(1.5.dp, Pal.LINE),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = Pal.TX)) { Text(text, fontWeight = FontWeight.SemiBold, fontSize = 16.sp) }

@Composable
fun Chip(text: String, color: Color = Pal.ORANGE, tag: String = "chip") {
    Row(Modifier.testTag(tag).clip(RoundedCornerShape(16.dp)).background(Color(0xFF2B1812)).border(1.5.dp, color, RoundedCornerShape(16.dp))
        .padding(horizontal = 12.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(10.dp).clip(CircleShape).background(color)); Spacer(Modifier.size(8.dp))
        Text(text, color = Pal.TX, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun Field(value: String, onChange: (String) -> Unit, hint: String, modifier: Modifier = Modifier, keyboard: KeyboardType = KeyboardType.Text, tag: String = "") =
    OutlinedTextField(value, onChange, modifier.fillMaxWidth().testTag(tag), placeholder = { Text(hint, color = Pal.TX3) }, singleLine = false,
        keyboardOptions = KeyboardOptions(keyboardType = keyboard), shape = RoundedCornerShape(12.dp),
        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Pal.MINT, unfocusedBorderColor = Pal.LINE, focusedTextColor = Pal.TX, unfocusedTextColor = Pal.TX))

@Composable
fun Header(title: String, sub: String?, showStop: Boolean, onBack: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().statusBarsPadding().padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, color = Pal.TX, fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
            if (sub != null) Text(sub, color = Pal.TX2, fontSize = 13.sp, modifier = Modifier.testTag("route"))
        }
        if (showStop) Button({ Graph.scope.launch { Graph.stop() } }, Modifier.testTag("stop").heightIn(min = 48.dp), shape = RoundedCornerShape(24.dp),
            colors = ButtonDefaults.buttonColors(containerColor = Pal.RED, contentColor = Color(0xFF2A0A08))) {
            Box(Modifier.size(14.dp).background(Color(0xFF2A0A08), RoundedCornerShape(3.dp))); Spacer(Modifier.size(8.dp))
            Text(stringResource(R.string.stop), fontWeight = FontWeight.ExtraBold, letterSpacing = 1.sp)
        }
    }
}

@Composable
fun routeText(): String {
    val online by Graph.online.collectAsState(); val via by Graph.via.collectAsState()
    return if (online) stringResource(R.string.route_connected, routeName(via)) else stringResource(R.string.route_offline)
}

fun fmtLeft(sec: Long) = if (sec >= 3600) "${sec / 3600} h ${(sec % 3600) / 60} min" else "${sec / 60} min ${sec % 60} s"

// ============================================================================================ root
@Composable
fun App(activity: FragmentActivity) = TurboTheme {
    var paired by remember { mutableStateOf(Graph.prefs.paired) }
    var onboarded by remember { mutableStateOf(Graph.prefs.onboarded) }
    val expSec by Graph.sessionExp.collectAsState()
    val sid by Graph.sessionId.collectAsState()
    val tick by produceState(0L) { while (true) { value = System.currentTimeMillis() / 1000; delay(1000) } }
    val sessionOpen = sid.isNotBlank() && expSec > tick
    when {
        !paired && !onboarded -> Welcome { onboarded = true; Graph.prefs.onboarded = true }
        !paired -> PairScreen(activity) { paired = true }
        !sessionOpen -> OpenSession(activity, onUnpair = { Graph.unpairLocal(); paired = false })
        else -> Main(activity, tick, expSec) { Graph.unpairLocal(); paired = false }
    }
}

// ============================================================================================ 1 welcome
@Composable
fun Welcome(onDone: () -> Unit) {
    var sel by remember { mutableStateOf(0) }
    val names = listOf(R.string.preset_easy, R.string.preset_balanced, R.string.preset_strict)
    val tags = listOf(R.string.preset_easy_tag, R.string.preset_balanced_tag, R.string.preset_strict_tag)
    val descs = listOf(R.string.preset_easy_desc, R.string.preset_balanced_desc, R.string.preset_strict_desc)
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).navigationBarsPadding()) {
        Header(stringResource(R.string.wel_title), stringResource(R.string.wel_sub), false)
        Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.wel_step, 1), color = Pal.MINT, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            names.indices.forEach { i ->
                val on = sel == i
                Row(Modifier.fillMaxWidth().testTag("preset$i").clip(RoundedCornerShape(20.dp)).background(if (on) Pal.S2 else Pal.S1)
                    .border(1.5.dp, if (on) Pal.MINT else Pal.LINE, RoundedCornerShape(20.dp)).selectable(on) { sel = i }.padding(16.dp)) {
                    Box(Modifier.padding(top = 4.dp).size(22.dp).border(2.dp, if (on) Pal.MINT else Pal.TX3, CircleShape).padding(5.dp)) {
                        if (on) Box(Modifier.fillMaxSize().background(Pal.MINT, CircleShape))
                    }
                    Column(Modifier.padding(start = 14.dp)) {
                        Text(stringResource(names[i]), color = Pal.TX, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        Text(stringResource(tags[i]), color = if (on) Pal.MINT else Pal.TX2, fontSize = 13.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(top = 4.dp))
                        Text(stringResource(descs[i]), color = Pal.TX2, fontSize = 14.sp, modifier = Modifier.padding(top = 8.dp))
                    }
                }
            }
            PrimaryButton(stringResource(R.string.preset_use, stringResource(names[sel])), Modifier.testTag("usePreset")) { Graph.prefs.preset = listOf("easy", "balanced", "strict")[sel]; onDone() }
            Text(stringResource(R.string.wel_foot), color = Pal.TX3, fontSize = 13.sp, modifier = Modifier.padding(bottom = 16.dp))
        }
    }
}

// ============================================================================================ 2 pairing
@androidx.annotation.OptIn(ExperimentalGetImage::class)
@Composable
fun QrScanner(modifier: Modifier, onText: (String) -> Unit) {
    val ctx = LocalContext.current
    val owner = LocalLifecycleOwner.current
    AndroidView(modifier = modifier, factory = { c ->
        PreviewView(c).also { pv ->
            val fut = ProcessCameraProvider.getInstance(c)
            fut.addListener({
                val provider = fut.get()
                val preview = Preview.Builder().build().also { it.setSurfaceProvider(pv.surfaceProvider) }
                val scanner = BarcodeScanning.getClient(BarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build())
                val analysis = ImageAnalysis.Builder().setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build().also { a ->
                    a.setAnalyzer(ContextCompat.getMainExecutor(c)) { proxy ->
                        val media = proxy.image
                        if (media == null) proxy.close() else
                            scanner.process(InputImage.fromMediaImage(media, proxy.imageInfo.rotationDegrees))
                                .addOnSuccessListener { codes -> codes.firstOrNull()?.rawValue?.let(onText) }
                                .addOnCompleteListener { proxy.close() }
                    }
                }
                try { provider.unbindAll(); provider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis) } catch (_: Exception) {}
            }, ContextCompat.getMainExecutor(ctx))
        }
    })
}

@Composable
fun PairScreen(activity: FragmentActivity, onPaired: () -> Unit) {
    val scope = rememberCoroutineScope()
    var camOk by remember { mutableStateOf(ContextCompat.checkSelfPermission(activity, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
    val askCam = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { camOk = it }
    LaunchedEffect(Unit) { if (!camOk) askCam.launch(Manifest.permission.CAMERA) }
    var paste by remember { mutableStateOf("") }; var code by remember { mutableStateOf("") }; var url by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val status by Graph.status.collectAsState()
    fun doPair(text: String?) = scope.launch {
        if (busy) return@launch
        busy = true
        // pairing is signed by the biometric-gated key too, so the prompt comes first
        if (Biometric.authenticate(activity) && Graph.pair(text, url.ifBlank { null }, code.ifBlank { null })) onPaired()
        busy = false
    }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).navigationBarsPadding()) {
        Header(stringResource(R.string.pair_title), stringResource(R.string.pair_sub), false)
        Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(stringResource(R.string.wel_step, 2), color = Pal.MINT, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            Text(stringResource(R.string.pair_run), color = Pal.TX2, fontSize = 15.sp)
            Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Pal.S2).padding(12.dp)) {
                Text("python -m turbo_hub pair", color = Pal.MINT, fontFamily = FontFamily.Monospace, fontSize = 15.sp)
            }
            Box(Modifier.fillMaxWidth().height(250.dp).clip(RoundedCornerShape(20.dp)).background(Color.Black), contentAlignment = Alignment.Center) {
                if (camOk) {
                    QrScanner(Modifier.fillMaxSize()) { t -> if (t.startsWith("turbo-pair:") && !busy) doPair(t) }
                    Text(stringResource(R.string.pair_scan), color = Pal.TX, fontSize = 14.sp, modifier = Modifier.align(Alignment.BottomCenter).padding(12.dp)
                        .background(Color(0x99000000), RoundedCornerShape(8.dp)).padding(8.dp))
                } else Text(stringResource(R.string.pair_camera_off), color = Pal.TX2, modifier = Modifier.padding(16.dp))
            }
            Text(stringResource(R.string.pair_manual), color = Pal.TX2, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Field(paste, { paste = it }, stringResource(R.string.pair_paste), tag = "pairPaste")
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Field(code, { code = it }, stringResource(R.string.pair_code), Modifier.weight(1f), KeyboardType.Number, "pairCode")
                Field(url, { url = it }, stringResource(R.string.pair_url), Modifier.weight(1f), KeyboardType.Uri, "pairUrl")
            }
            if (status.isNotBlank()) Text(status, color = Pal.AMBER, fontSize = 14.sp, modifier = Modifier.testTag("status"))
            TCard(fill = Color(0xFF2A2416)) { Text(stringResource(R.string.pair_fp_note), color = Pal.AMBER, fontSize = 14.sp, fontWeight = FontWeight.SemiBold) }
            PrimaryButton(stringResource(R.string.pair_button), Modifier.testTag("pairButton")) { doPair(paste.ifBlank { null }) }
            Spacer(Modifier.height(16.dp))
        }
    }
}

// ============================================================================================ 6 open session
@Composable
fun OpenSession(activity: FragmentActivity, onUnpair: () -> Unit) {
    val scope = rememberCoroutineScope()
    var code by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    val status by Graph.status.collectAsState()
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).navigationBarsPadding()) {
        Header(stringResource(R.string.sess_title), stringResource(R.string.sess_expired), false)
        Column(Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            TCard {
                Column { Text(stringResource(R.string.sess_info1), color = Pal.TX, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                    Text(stringResource(R.string.sess_info2), color = Pal.TX2, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp)) }
            }
            Text(stringResource(R.string.sess_code_label), color = Pal.TX2, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            Field(code, { if (it.length <= 6 && it.all(Char::isDigit)) code = it }, "000000", keyboard = KeyboardType.NumberPassword, tag = "totp")
            Text(stringResource(R.string.sess_hint), color = Pal.TX3, fontSize = 13.sp)
            if (status.isNotBlank()) Text(status, color = Pal.AMBER, fontSize = 14.sp, modifier = Modifier.testTag("status"))
            PrimaryButton(stringResource(R.string.sess_button), Modifier.testTag("openSession")) {
                scope.launch { if (!busy) { busy = true; if (Biometric.authenticate(activity)) Graph.openSession(code); busy = false } }
            }
            Text(stringResource(R.string.sess_foot), color = Pal.TX3, fontSize = 13.sp)
            GhostButton(stringResource(R.string.set_unpair), Modifier.testTag("unpairSession")) { scope.launch { Graph.unpairRemote(); onUnpair() } }
        }
    }
}

// ============================================================================================ main shell
@Composable
fun Main(activity: FragmentActivity, nowSec: Long, expSec: Long, onUnpair: () -> Unit) {
    var tab by remember { mutableStateOf(Tab.TASKS) }
    val rawIndicator by Graph.indicator.collectAsState()
    val running by Graph.taskRunning.collectAsState()
    val indicator = if (rawIndicator == "idle" && running) "acting" else rawIndicator   // a running task is never "ready"
    val stopped by Graph.stopped.collectAsState()
    val pulse by rememberInfiniteTransition(label = "glow").animateFloat(0.35f, 1f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "a")
    val frame = when {
        stopped -> Modifier
        indicator == "input_locked" -> Modifier.border(6.dp, Pal.ORANGE)
        indicator == "acting" -> Modifier.border(3.dp, Pal.ORANGE.copy(alpha = pulse))
        else -> Modifier
    }
    val wantedTab by Graph.requestTab.collectAsState()
    LaunchedEffect(wantedTab) { wantedTab?.let { n -> Tab.entries.firstOrNull { it.name == n }?.let { tab = it } } }
    LaunchedEffect(Unit) { Graph.refreshTasks() }
    Box(Modifier.fillMaxSize().then(frame).testTag("frame_$indicator")) {
        Column(Modifier.fillMaxSize()) {
            Header(stringResource(when (tab) { Tab.TASKS -> R.string.tab_tasks; Tab.LIVE -> R.string.live_title; Tab.APPROVALS -> R.string.appr_title
                Tab.AUDIT -> R.string.audit_title; Tab.SETTINGS -> R.string.set_title }), routeText(), true)
            Box(Modifier.weight(1f).fillMaxWidth()) {
                Column(Modifier.fillMaxSize()) {
                    if (stopped) StopCard()
                    when (tab) {
                        Tab.TASKS -> TasksTab(activity, nowSec, expSec)
                        Tab.LIVE -> LiveTab()
                        Tab.APPROVALS -> ApprovalsTab(activity)
                        Tab.AUDIT -> AuditTab()
                        Tab.SETTINGS -> SettingsTab(activity, onUnpair)
                    }
                }
            }
            val pending by Graph.pending.collectAsState()
            Row(Modifier.fillMaxWidth().background(Pal.S1).navigationBarsPadding().padding(vertical = 6.dp)) {
                Tab.entries.forEach { t ->
                    val on = t == tab
                    Column(Modifier.weight(1f).heightIn(min = 56.dp).testTag("tab_${t.name}").selectable(on) { tab = t }, horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center) {
                        Box(Modifier.clip(RoundedCornerShape(16.dp)).background(if (on) Color(0xFF1F3B33) else Color.Transparent).padding(horizontal = 18.dp, vertical = 4.dp)) {
                            Text(t.glyph + if (t == Tab.APPROVALS && pending.isNotEmpty()) " ${pending.size}" else "", color = if (on) Pal.MINT else Pal.TX2, fontSize = 18.sp)
                        }
                        Text(stringResource(t.label), color = if (on) Pal.TX else Pal.TX3, fontSize = 12.sp, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal)
                    }
                }
            }
        }
    }
}

@Composable
fun StopCard() {
    TCard(Modifier.padding(16.dp).testTag("stopCard"), Color(0xFF2A1513), Pal.RED) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.stop_title), color = Pal.TX, fontSize = 26.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = 2.sp)
            Text(stringResource(R.string.stop_sub), color = Pal.TX2, fontSize = 14.sp, modifier = Modifier.padding(vertical = 8.dp))
            PrimaryButton(stringResource(R.string.stop_resume), Modifier.testTag("resume"), Pal.TX, Pal.BG) { Graph.scope.launch { Graph.resume() } }
            Text(stringResource(R.string.stop_hotkey), color = Pal.TX3, fontSize = 13.sp, modifier = Modifier.padding(top = 8.dp))
        }
    }
}

// ============================================================================================ 3 tasks
@Composable
fun TasksTab(activity: FragmentActivity, nowSec: Long, expSec: Long) {
    val scope = rememberCoroutineScope()
    var text by remember { mutableStateOf("") }
    val day by Graph.dayUsage.collectAsState(); val tasks by Graph.tasks.collectAsState(); val status by Graph.status.collectAsState()
    val online by Graph.online.collectAsState()
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        TCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(12.dp).clip(CircleShape).background(if (online) Pal.MINT else Pal.AMBER))
                Column(Modifier.padding(start = 12.dp).weight(1f)) {
                    Text(stringResource(R.string.sess_left, fmtLeft((expSec - nowSec).coerceAtLeast(0))), color = Pal.TX, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.testTag("sessionLeft"))
                    Text(stringResource(R.string.home_usage, day.input + day.output, "%.2f".format(day.cost)), color = Pal.TX2, fontSize = 13.sp)
                }
                Text(stringResource(R.string.sess_extend), color = Pal.MINT, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.clip(RoundedCornerShape(8.dp)).selectable(false) {
                    Graph.prefs.sessionId = ""; Graph.sessionId.value = ""; Graph.sessionExp.value = 0 }.padding(8.dp))
            }
        }
        Text(stringResource(R.string.home_give), color = Pal.TX2, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
        Field(text, { text = it }, stringResource(R.string.home_example), Modifier.heightIn(min = 120.dp), tag = "taskInput")
        Text(stringResource(R.string.home_hint), color = Pal.TX3, fontSize = 13.sp)
        if (status.isNotBlank()) Text(status, color = Pal.AMBER, fontSize = 14.sp, modifier = Modifier.testTag("status"))
        PrimaryButton(stringResource(R.string.home_send), Modifier.testTag("sendTask")) {
            if (text.isNotBlank()) scope.launch { if (Graph.sendTask(text.trim())) { text = ""; Graph.refreshTasks() } }
        }
        Text(stringResource(R.string.home_recent), color = Pal.TX2, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
        tasks.take(8).forEach { t ->
            val st = t.optString("status")
            TCard { Column {
                Text(t.optString("text"), color = Pal.TX, fontSize = 16.sp, fontWeight = FontWeight.Medium, maxLines = 2)
                Text(st, color = if (st == "done") Pal.MINT else if (st == "running") Pal.TX2 else Pal.AMBER, fontSize = 13.sp)
            } }
        }
        Spacer(Modifier.height(8.dp))
    }
}

// ============================================================================================ 4 live
@Composable
fun LiveTab() {
    val ctx = LocalContext.current
    val events by Graph.events.collectAsState(); val indicator by Graph.indicator.collectAsState(); val paused by Graph.paused.collectAsState()
    val usage by Graph.sessionUsage.collectAsState(); val locked by Graph.inputLocked.collectAsState()
    val taskRunning by Graph.taskRunning.collectAsState(); val taskUsage by Graph.taskUsage.collectAsState()
    val shown = events.filter { it.type in setOf("task_started", "text", "tool_call", "tool_result", "approval_request", "approval_resolved", "final", "task_finished", "warning", "hub_alert", "stopped", "input_lock", "taken_over") }.takeLast(60)
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        when {
            locked || indicator == "input_locked" -> Chip(stringResource(R.string.chip_locked), tag = "chipLocked")
            indicator == "acting" || taskRunning -> Chip(stringResource(R.string.chip_acting), tag = "chipActing")
            else -> Chip(stringResource(R.string.chip_idle), Pal.MINT, "chipIdle")
        }
        if (shown.isEmpty()) Text(stringResource(R.string.live_idle), color = Pal.TX2, fontSize = 14.sp)
        LazyColumn(Modifier.weight(1f).testTag("events"), reverseLayout = true, verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(shown.reversed()) { e ->
                Row {
                    Text(java.text.SimpleDateFormat("HH:mm:ss").format(java.util.Date((e.json.optDouble("ts") * 1000).toLong())), color = Pal.TX3, fontSize = 12.sp, fontFamily = FontFamily.Monospace, modifier = Modifier.padding(end = 10.dp, top = 2.dp))
                    Text(e.line(ctx).take(220), color = if (e.type == "hub_alert") Pal.RED else Pal.TX, fontSize = 14.sp)
                }
            }
        }
        TCard(fill = Pal.S1) { Column {
            Text(stringResource(R.string.live_this), color = Pal.TX3, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            Text(taskUsage?.let { u -> if (u.cost > 0) stringResource(R.string.live_usage_cost, u.input + u.cacheRead, u.output, "%.4f".format(u.cost)) else stringResource(R.string.live_usage, u.input + u.cacheRead, u.output) } ?: stringResource(R.string.live_usage_none), color = Pal.TX, fontSize = 15.sp, modifier = Modifier.testTag("usage"))
        } }
        if (paused) PrimaryButton(stringResource(R.string.live_resume), Modifier.testTag("resumePaused")) { Graph.scope.launch { Graph.resume() } }
        else {
            val urgent = locked || indicator == "input_locked"
            if (urgent) PrimaryButton(stringResource(R.string.takeover_button), Modifier.testTag("takeover"), Pal.ORANGE, Color.White) { Graph.scope.launch { Graph.takeOver() } }
            else GhostButton(stringResource(R.string.takeover_button), Modifier.testTag("takeover")) { Graph.scope.launch { Graph.takeOver() } }
            Text(stringResource(R.string.live_takeover_hint), color = Pal.TX3, fontSize = 12.sp, modifier = Modifier.padding(bottom = 8.dp))
        }
    }
}

// ============================================================================================ 5 approvals
@Composable
fun ApprovalsTab(activity: FragmentActivity) {
    val pending by Graph.pending.collectAsState()
    val scope = rememberCoroutineScope()
    val now by produceState(System.currentTimeMillis() / 1000.0) { while (true) { value = System.currentTimeMillis() / 1000.0; delay(1000) } }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (pending.isEmpty()) Text(stringResource(R.string.appr_none), color = Pal.TX2, fontSize = 15.sp, modifier = Modifier.testTag("noApprovals"))
        pending.forEach { a ->
            TCard(Modifier.testTag("approval"), Pal.S1, Pal.AMBER) { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.appr_need), color = Pal.TX, fontSize = 20.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                    val left = (a.expiresAt - now).toLong().coerceAtLeast(0)
                    Text("%d:%02d".format(left / 60, left % 60), color = Pal.AMBER, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)
                }
                Text(stringResource(R.string.appr_wants, a.action, a.control), color = Pal.TX, fontSize = 18.sp, fontWeight = FontWeight.SemiBold)
                Text(stringResource(R.string.appr_in, a.window), color = Pal.TX2, fontSize = 14.sp)
                a.cropPng?.let { b -> BitmapFactory.decodeByteArray(b, 0, b.size)?.let { bmp ->
                    Image(bmp.asImageBitmap(), null, Modifier.fillMaxWidth().heightIn(max = 160.dp).clip(RoundedCornerShape(12.dp)).background(Pal.S2).testTag("crop"))
                    Text(stringResource(R.string.appr_crop), color = Pal.TX3, fontSize = 12.sp) } }
                Text(stringResource(R.string.appr_timeout), color = Pal.TX2, fontSize = 13.sp)
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    GhostButton(stringResource(R.string.appr_deny), Modifier.weight(1f).testTag("deny")) { scope.launch { if (Biometric.authenticate(activity)) Graph.decide(a.id, "deny") } }
                    PrimaryButton(stringResource(R.string.appr_allow), Modifier.weight(1f).testTag("allow"), Pal.AMBER, Color(0xFF2A1B00)) { scope.launch { if (Biometric.authenticate(activity)) Graph.decide(a.id, "allow") } }
                }
                Text(stringResource(R.string.appr_bio), color = Pal.TX3, fontSize = 12.sp)
            } }
        }
    }
}

// ============================================================================================ 8 audit
@Composable
fun AuditTab() {
    val entries by Graph.audit.collectAsState(); val ok by Graph.auditOk.collectAsState()
    LaunchedEffect(Unit) { Graph.refreshAudit() }
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        TCard(fill = if (ok == false) Color(0xFF3A1815) else Color(0xFF16302A), modifier = Modifier.testTag("auditChain")) {
            Text(if (ok == false) stringResource(R.string.audit_bad) else stringResource(R.string.audit_ok, entries.size), color = Pal.TX, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
        }
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(entries) { e ->
                Column {
                    Row { Text(java.text.SimpleDateFormat("HH:mm:ss").format(java.util.Date((e.optDouble("ts") * 1000).toLong())), color = Pal.TX3, fontSize = 12.sp, fontFamily = FontFamily.Monospace)
                        Text("  " + e.optString("kind"), color = if (e.optString("kind") in setOf("rejected", "stop", "lockout")) Pal.RED else if (e.optString("kind").startsWith("approval")) Pal.AMBER else Pal.TX2, fontSize = 12.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold) }
                    Text(e.optJSONObject("data")?.toString()?.take(140) ?: "", color = Pal.TX, fontSize = 14.sp)
                }
            }
        }
        val scope = rememberCoroutineScope()
        GhostButton(stringResource(R.string.audit_refresh), Modifier.testTag("auditRefresh")) { scope.launch { Graph.refreshAudit() } }
        Text(stringResource(R.string.audit_foot), color = Pal.TX3, fontSize = 13.sp, modifier = Modifier.padding(bottom = 8.dp))
    }
}

// ============================================================================================ 7 settings
@Composable
fun SettingRow(title: String, desc: String, tag: String, trailing: @Composable () -> Unit) {
    TCard(Modifier.testTag(tag)) {
        Row(verticalAlignment = Alignment.Top) {
            // the text column takes the remaining width, so a long description wraps BEFORE the toggle (never under it)
            Column(Modifier.weight(1f).padding(end = 12.dp)) {
                Text(title, color = Pal.TX, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Text(desc, color = Pal.TX2, fontSize = 13.sp, modifier = Modifier.padding(top = 4.dp))
            }
            trailing()
        }
    }
}

@Composable
fun SettingsTab(activity: FragmentActivity, onUnpair: () -> Unit) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val policy by Graph.policy.collectAsState()
    val presetName = policy?.optString("preset")?.ifBlank { null } ?: Graph.prefs.preset.ifBlank { "easy" }
    val lockMode = policy?.optString("lockMode") ?: "real_input"
    var url by remember { mutableStateOf("") }; var relayUrl by remember { mutableStateOf(Graph.prefs.relayUrl) }; var relayCode by remember { mutableStateOf("") }
    val wake by Graph.wakeState.collectAsState()
    var showCf by remember { mutableStateOf(false) }
    if (showCf) { CfLogin { showCf = false }; return }
    LaunchedEffect(Unit) { Graph.refreshTasks() }
    @Composable fun group(label: Int, color: Color) = Text(stringResource(label), color = color, fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp, modifier = Modifier.padding(top = 8.dp))
    fun on(key: String, def: Boolean) = policy?.optBoolean(key, def) ?: def
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(stringResource(R.string.set_level, stringResource(when (presetName) { "balanced" -> R.string.preset_balanced; "strict" -> R.string.preset_strict; else -> R.string.preset_easy })), color = Pal.TX2, fontSize = 14.sp, modifier = Modifier.testTag("level"))
        Text(stringResource(R.string.set_pc_note), color = Pal.TX3, fontSize = 13.sp)
        group(R.string.set_g_basic, Pal.MINT)
        SettingRow(stringResource(R.string.set_row_floor), stringResource(R.string.set_row_floor_d), "row_floor") { Column(horizontalAlignment = Alignment.CenterHorizontally) { Switch(true, null, enabled = false); Text("🔒", fontSize = 12.sp) } }
        group(R.string.set_g_mid, Pal.AMBER)
        SettingRow(stringResource(R.string.set_row_ask), stringResource(R.string.set_row_ask_d), "row_ask") { Switch((policy?.optJSONArray("ask")?.length() ?: 4) > 0, null, enabled = false) }
        SettingRow(stringResource(R.string.set_row_totp), stringResource(R.string.set_row_totp_d), "row_totp") { Switch(on("totp", false), null, enabled = false) }
        SettingRow(stringResource(R.string.set_row_lock), stringResource(R.string.set_row_lock_d), "row_lock") {
            Text(stringResource(if (lockMode == "whole_task") R.string.set_lock_task else R.string.set_lock_real) + " ›", color = Pal.MINT, fontSize = 14.sp, fontWeight = FontWeight.SemiBold) }
        SettingRow(stringResource(R.string.set_row_border), stringResource(R.string.set_row_border_d), "row_border") { Column(horizontalAlignment = Alignment.CenterHorizontally) { Switch(true, null, enabled = false); Text("🔒", fontSize = 12.sp) } }
        group(R.string.set_g_strict, Pal.RED)
        SettingRow(stringResource(R.string.set_row_bio), stringResource(R.string.set_row_bio_d), "row_bio") { Switch(on("biometric", false), null, enabled = false) }
        SettingRow(stringResource(R.string.set_row_cf), stringResource(R.string.set_row_cf_d), "row_cf") { Switch(on("cfAccess", false), null, enabled = false) }
        group(R.string.set_conn, Pal.TX2)
        Graph.prefs.urls.forEach { (n, u) -> Text("$n: $u", color = Pal.TX2, fontSize = 13.sp, fontFamily = FontFamily.Monospace) }
        Field(url, { url = it }, stringResource(R.string.set_url_hint), keyboard = KeyboardType.Uri, tag = "addUrl")
        GhostButton(stringResource(R.string.set_url_add), Modifier.testTag("addUrlButton")) { if (url.isNotBlank()) { Graph.prefs.setUrl(Protocol.transportName(url), url); url = "" } }
        GhostButton(stringResource(R.string.set_access_login)) { showCf = true }
        group(R.string.set_wake, Pal.TX2)
        Field(relayUrl, { relayUrl = it }, stringResource(R.string.set_wake_relay), keyboard = KeyboardType.Uri, tag = "relayUrl")
        Field(relayCode, { relayCode = it }, stringResource(R.string.set_wake_pair), keyboard = KeyboardType.Number)
        GhostButton(stringResource(R.string.set_wake_pair)) { scope.launch { try { Graph.relay.pair(relayUrl, relayCode, "phone") } catch (e: Exception) { Graph.fail(e) } } }
        PrimaryButton(stringResource(R.string.set_wake_button), Modifier.testTag("wake")) { Graph.prefs.relayUrl = relayUrl; scope.launch { Graph.wakePc() } }
        if (wake.isNotBlank()) Text(wake, color = Pal.AMBER, fontSize = 14.sp, modifier = Modifier.testTag("wakeState"))
        group(R.string.set_battery, Pal.TX2)
        Text(stringResource(R.string.set_battery_d), color = Pal.TX2, fontSize = 13.sp)
        GhostButton(stringResource(R.string.set_battery_open), Modifier.testTag("battery")) { BatteryGuide.available(ctx).firstOrNull()?.let { BatteryGuide.open(ctx, it) } }
        GhostButton(stringResource(R.string.set_unpair), Modifier.testTag("unpair")) { scope.launch { Graph.unpairRemote(); onUnpair() } }
        Text(stringResource(R.string.set_language), color = Pal.TX3, fontSize = 12.sp, modifier = Modifier.padding(bottom = 16.dp))
    }
}

/** Cloudflare Access: log in inside a WebView once, keep the CF_Authorization cookie for the app's requests. */
@Composable
fun CfLogin(onDone: () -> Unit) {
    val target = Graph.prefs.urls.firstOrNull { it.first == "cloudflare" }?.second
    Column(Modifier.fillMaxSize().statusBarsPadding()) {
        if (target != null) AndroidView(factory = { c -> WebView(c).apply { settings.javaScriptEnabled = true; loadUrl(target) } }, modifier = Modifier.weight(1f).fillMaxWidth())
        else Text(stringResource(R.string.set_url_hint), color = Pal.TX2, modifier = Modifier.weight(1f).padding(16.dp))
        PrimaryButton("OK", Modifier.padding(16.dp).testTag("cfDone")) {
            target?.let { u -> CookieManager.getInstance().getCookie(u)?.split(";")?.map { it.trim() }?.firstOrNull { it.startsWith("CF_Authorization=") }
                ?.let { Graph.prefs.cfCookie = it.removePrefix("CF_Authorization=") } }
            onDone()
        }
    }
}
