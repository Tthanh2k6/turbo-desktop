package dev.turbodesktop.remote

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Assignment
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.automirrored.rounded.Assignment
import androidx.compose.material.icons.outlined.BarChart
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.VerifiedUser
import androidx.compose.material.icons.rounded.BarChart
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material.icons.rounded.ContentCopy
import androidx.compose.material.icons.rounded.DesktopWindows
import androidx.compose.material.icons.rounded.Settings
import androidx.compose.material.icons.rounded.Stop
import androidx.compose.material.icons.rounded.VerifiedUser
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import kotlinx.coroutines.launch
import java.text.NumberFormat

val LocalInMainShell = compositionLocalOf { false }

enum class Tab(val label: Int) {
    TASKS(R.string.tab_tasks),
    APPROVALS(R.string.tab_approvals),
    REPORT(R.string.tab_report),
    SETTINGS(R.string.tab_settings);

    fun icon(selected: Boolean): ImageVector = when (this) {
        TASKS -> if (selected) Icons.AutoMirrored.Rounded.Assignment else Icons.AutoMirrored.Outlined.Assignment
        APPROVALS -> if (selected) Icons.Rounded.VerifiedUser else Icons.Outlined.VerifiedUser
        REPORT -> if (selected) Icons.Rounded.BarChart else Icons.Outlined.BarChart
        SETTINGS -> if (selected) Icons.Rounded.Settings else Icons.Outlined.Settings
    }
}

fun routeName(v: String): String = when (v.lowercase()) {
    "lan" -> "LAN"
    "tailscale" -> "Tailscale"
    "cloudflare" -> "Cloudflare"
    "local" -> "Local"
    "-", "" -> ""
    else -> v.replaceFirstChar { it.uppercase() }
}

fun pcDisplayName(ctx: Context): String {
    (try { Graph.prefs.pcName } catch (_: Exception) { "" }).takeIf { it.isNotBlank() }?.let { return it }
    val urls = try { Graph.prefs.urls } catch (_: Exception) { emptyList() }
    val active = try { Graph.prefs.activePath } catch (_: Exception) { "" }
    val chosen = urls.firstOrNull { it.first == active }?.second ?: urls.firstOrNull()?.second.orEmpty()
    val host = chosen.substringAfter("://", "").substringBefore("/").substringBefore(":").trim()
    val isIpOrLocal = host.isBlank() ||
        host.equals("localhost", ignoreCase = true) ||
        host.all { it.isDigit() || it == '.' } ||
        host.contains(':')
    return if (isIpOrLocal) ctx.getString(R.string.pc_default_name) else host.substringBefore('.').uppercase()
}

fun fmtLeft(ctx: Context, sec: Long): String = when {
    sec >= 3600 -> ctx.getString(R.string.time_hm, sec / 3600, (sec % 3600) / 60)
    sec >= 60 -> ctx.getString(R.string.time_ms, sec / 60, sec % 60)
    else -> ctx.getString(R.string.time_s, sec)
}

fun fmtInt(n: Long): String = NumberFormat.getIntegerInstance().format(n)

fun copyPlainText(ctx: Context, label: String, text: String) {
    val cm = ctx.getSystemService(ClipboardManager::class.java) ?: return
    cm.setPrimaryClip(ClipData.newPlainText(label, text))
}

fun readClipboardSixDigits(ctx: Context): String? {
    val cm = ctx.getSystemService(ClipboardManager::class.java) ?: return null
    val raw = cm.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.coerceToText(ctx)?.toString() ?: return null
    val exactRun = Regex("\\b(\\d{6})\\b").find(raw)?.groupValues?.get(1)
    if (exactRun != null) return exactRun
    val digits = raw.filter(Char::isDigit)
    return if (digits.length >= 6) digits.take(6) else null
}

/**
 * Runs [Biometric.authenticate] before [action] only when [biometricRequired] is true.
 * If [biometricRequired] is false, runs [action] directly and falls back to biometric only if Android Keystore's
 * auth-gated key reports an expired 30 s authentication window.
 */
suspend fun runWithBiometricIfNeeded(
    activity: FragmentActivity,
    biometricRequired: Boolean,
    action: suspend () -> Boolean,
): Boolean {
    if (biometricRequired) {
        if (!Biometric.authenticate(activity)) return false
        return action()
    }
    val ok = action()
    if (!ok && Graph.status.value.contains("authenticated", ignoreCase = true)) {
        Graph.status.value = ""
        if (Biometric.authenticate(activity)) return action()
    }
    return ok
}

@Composable
fun PresenceHeader(modifier: Modifier = Modifier) {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    val online by Graph.online.collectAsState()
    val via by Graph.via.collectAsState()
    val stopped by Graph.stopped.collectAsState()
    val paused by Graph.paused.collectAsState()
    val inputLocked by Graph.inputLocked.collectAsState()
    val rawIndicator by Graph.indicator.collectAsState()
    val taskRunning by Graph.taskRunning.collectAsState()

    val isLocked = !stopped && !paused && (inputLocked || rawIndicator == "input_locked")
    val isActing = !stopped && !paused && !isLocked && (rawIndicator == "acting" || taskRunning)

    val dotColor: Color
    val stateTextColor: Color
    val stateLabel: String
    when {
        !online -> {
            dotColor = c.warn
            stateTextColor = c.warn
            stateLabel = stringResource(R.string.route_offline)
        }
        stopped -> {
            dotColor = c.stop
            stateTextColor = c.stopText
            stateLabel = stringResource(R.string.title_stopped)
        }
        paused -> {
            dotColor = c.warn
            stateTextColor = c.warn
            stateLabel = stringResource(R.string.presence_paused)
        }
        isLocked -> {
            dotColor = c.ai
            stateTextColor = c.aiText
            stateLabel = stringResource(R.string.presence_locked)
        }
        isActing -> {
            dotColor = c.ai
            stateTextColor = c.aiText
            stateLabel = stringResource(R.string.chip_acting)
        }
        else -> {
            dotColor = c.primary
            stateTextColor = c.onSurfaceVariant
            stateLabel = stringResource(R.string.chip_idle)
        }
    }

    val routePart = routeName(via).ifBlank {
        if (online) "Local" else stringResource(R.string.route_offline)
    }

    Row(
        modifier = modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .padding(horizontal = TurboSpacing.gutter, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(TurboRadii.medium)
                .background(c.surfaceContainerHigh),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = Icons.Rounded.DesktopWindows,
                contentDescription = null,
                tint = c.onSurfaceVariant,
                modifier = Modifier.size(22.dp),
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = pcDisplayName(ctx),
                    style = MaterialTheme.typography.titleMedium,
                    color = c.onSurface,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    text = " · $routePart",
                    style = MaterialTheme.typography.bodySmall,
                    color = c.muted,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.testTag("route"),
                )
            }
            Spacer(Modifier.height(2.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(contentAlignment = Alignment.Center, modifier = Modifier.size(14.dp)) {
                    if (isLocked) {
                        Box(
                            Modifier
                                .size(14.dp)
                                .border(1.5.dp, c.ai.copy(alpha = 0.6f), TurboRadii.full)
                        )
                    }
                    Box(
                        Modifier
                            .size(8.dp)
                            .clip(TurboRadii.full)
                            .background(dotColor)
                    )
                }
                Spacer(Modifier.width(6.dp))
                Text(
                    text = stateLabel,
                    style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.SemiBold),
                    color = stateTextColor,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        if (!stopped) {
            Spacer(Modifier.width(8.dp))
            Button(
                onClick = { Graph.scope.launch { Graph.stop() } },
                modifier = Modifier
                    .testTag("stop")
                    .defaultMinSize(minHeight = TurboSpacing.touchMin),
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
                    modifier = Modifier.size(22.dp),
                )
                Spacer(Modifier.width(4.dp))
                Text(
                    text = stringResource(R.string.stop),
                    fontFamily = BeVietnamPro,
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp,
                    letterSpacing = 1.2.sp,
                )
            }
        }
    }
}

@Composable
fun SessionTopHeader() {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    val online by Graph.online.collectAsState()
    val via by Graph.via.collectAsState()
    val routeStr = if (online) {
        stringResource(R.string.route_connected, routeName(via).ifBlank { "Local" })
    } else {
        val known = routeName(via)
        if (known.isNotBlank()) "$known · ${stringResource(R.string.route_offline)}"
        else stringResource(R.string.route_offline)
    }

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .padding(horizontal = TurboSpacing.gutter, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            modifier = Modifier
                .size(40.dp)
                .clip(TurboRadii.medium)
                .background(c.surfaceContainerHigh),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = Icons.Rounded.DesktopWindows,
                contentDescription = null,
                tint = c.onSurfaceVariant,
                modifier = Modifier.size(22.dp),
            )
        }
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                text = pcDisplayName(ctx),
                style = MaterialTheme.typography.titleMedium,
                color = c.onSurface,
            )
            Spacer(Modifier.height(2.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    Modifier
                        .size(8.dp)
                        .clip(TurboRadii.full)
                        .background(if (online) c.primary else c.warn)
                )
                Spacer(Modifier.width(6.dp))
                Text(
                    text = routeStr,
                    style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium),
                    color = c.onSurfaceVariant,
                    modifier = Modifier.testTag("route"),
                )
            }
        }
    }
}

@Composable
fun StepperHeader(
    step: Int,
    total: Int = 3,
    onBack: (() -> Unit)? = null,
) {
    val c = LocalTurboColors.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .padding(
                start = if (onBack != null) 4.dp else TurboSpacing.gutter,
                end = TurboSpacing.gutter,
                top = 8.dp,
                bottom = 8.dp,
            ),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (onBack != null) {
            IconButton(
                onClick = onBack,
                modifier = Modifier.size(TurboSpacing.touchMin),
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Rounded.ArrowBack,
                    contentDescription = stringResource(R.string.cd_back),
                    tint = c.onSurface,
                )
            }
            Spacer(Modifier.width(4.dp))
        }
        Column(Modifier.weight(1f)) {
            Text(
                text = stringResource(R.string.step_of, step, total),
                style = MaterialTheme.typography.labelMedium,
                color = c.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                for (i in 0 until total) {
                    Box(
                        Modifier
                            .weight(1f)
                            .height(4.dp)
                            .clip(RoundedCornerShape(2.dp))
                            .background(if (i < step) c.primary else c.surfaceContainerHighest)
                    )
                }
            }
        }
    }
}

@Composable
fun PrimaryButton(
    text: String,
    modifier: Modifier = Modifier,
    color: Color = LocalTurboColors.current.primary,
    fg: Color = LocalTurboColors.current.onPrimary,
    leadingIcon: ImageVector? = null,
    trailingIcon: ImageVector? = null,
    minHeight: Dp = TurboSpacing.buttonPrimary,
    enabled: Boolean = true,
    onClick: () -> Unit,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = minHeight),
        shape = TurboRadii.full,
        colors = ButtonDefaults.buttonColors(
            containerColor = color,
            contentColor = fg,
            disabledContainerColor = LocalTurboColors.current.surfaceContainerHighest,
            disabledContentColor = LocalTurboColors.current.muted,
        ),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 12.dp),
    ) {
        if (leadingIcon != null) {
            Icon(leadingIcon, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text = text, style = if (minHeight >= 48.dp) TurboType.button else TurboType.buttonSmall)
        if (trailingIcon != null) {
            Spacer(Modifier.width(8.dp))
            Icon(trailingIcon, contentDescription = null, modifier = Modifier.size(18.dp))
        }
    }
}

@Composable
fun TonalButton(
    text: String,
    modifier: Modifier = Modifier,
    leadingIcon: ImageVector? = null,
    minHeight: Dp = TurboSpacing.buttonPrimary,
    onClick: () -> Unit,
) {
    val c = LocalTurboColors.current
    PrimaryButton(
        text = text,
        modifier = modifier,
        color = c.primaryContainer,
        fg = c.onPrimaryContainer,
        leadingIcon = leadingIcon,
        minHeight = minHeight,
        onClick = onClick,
    )
}

@Composable
fun GhostButton(
    text: String,
    modifier: Modifier = Modifier,
    leadingIcon: ImageVector? = null,
    minHeight: Dp = TurboSpacing.buttonSecondary,
    onClick: () -> Unit,
) {
    val c = LocalTurboColors.current
    OutlinedButton(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = minHeight),
        shape = TurboRadii.full,
        border = BorderStroke(1.dp, c.outline),
        colors = ButtonDefaults.outlinedButtonColors(contentColor = c.onSurface),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 10.dp),
    ) {
        if (leadingIcon != null) {
            Icon(leadingIcon, contentDescription = null, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
        }
        Text(text = text, style = TurboType.button)
    }
}

@Composable
fun TextActionButton(
    text: String,
    modifier: Modifier = Modifier,
    fg: Color = LocalTurboColors.current.primary,
    onClick: () -> Unit,
) {
    TextButton(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = TurboSpacing.buttonSecondary),
        shape = TurboRadii.full,
        colors = ButtonDefaults.textButtonColors(contentColor = fg),
    ) {
        Text(text = text, style = TurboType.button)
    }
}

@Composable
fun CodeBlock(
    command: String,
    modifier: Modifier = Modifier,
    copyable: Boolean = true,
    textColor: Color = LocalTurboColors.current.primary,
    onCopied: (() -> Unit)? = null,
) {
    val c = LocalTurboColors.current
    val ctx = LocalContext.current
    Row(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = 48.dp)
            .clip(TurboRadii.medium)
            .background(c.surfaceContainerHigh)
            .padding(start = 14.dp, end = if (copyable) 4.dp else 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = command,
            style = TurboType.monoCode,
            color = textColor,
            modifier = Modifier
                .weight(1f)
                .padding(vertical = 10.dp),
        )
        if (copyable) {
            IconButton(
                onClick = {
                    copyPlainText(ctx, command, command)
                    onCopied?.invoke()
                },
                modifier = Modifier.size(TurboSpacing.touchMin),
            ) {
                Icon(
                    imageVector = Icons.Rounded.ContentCopy,
                    contentDescription = stringResource(R.string.cd_copy),
                    tint = c.onSurfaceVariant,
                    modifier = Modifier.size(20.dp),
                )
            }
        }
    }
}

@Composable
fun KeycapRow(keys: List<String>, modifier: Modifier = Modifier) {
    val c = LocalTurboColors.current
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        keys.forEachIndexed { index, key ->
            Box(
                modifier = Modifier
                    .clip(TurboRadii.extraSmall)
                    .background(c.surfaceContainerHighest)
                    .border(1.dp, c.outline, TurboRadii.extraSmall)
                    .padding(horizontal = 10.dp, vertical = 4.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(text = key, style = TurboType.monoCode, color = c.onSurface)
            }
            if (index < keys.lastIndex) {
                Text(
                    text = "+",
                    style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium),
                    color = c.muted,
                )
            }
        }
    }
}

@Composable
fun OtpSixBoxInput(
    code: String,
    onCodeChange: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val c = LocalTurboColors.current
    val label = stringResource(R.string.sess_code_label)
    var focused by remember { mutableStateOf(false) }

    BasicTextField(
        value = code,
        onValueChange = { raw ->
            val clean = raw.filter(Char::isDigit).take(6)
            onCodeChange(clean)
        },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
        cursorBrush = SolidColor(Color.Transparent),
        modifier = modifier
            .fillMaxWidth()
            .onFocusChanged { focused = it.isFocused }
            .semantics { contentDescription = label }
            .testTag("totp"),
        decorationBox = { innerTextField ->
            Box {
                // Keep innerTextField in the composition so semantics/IME attach properly.
                Box(Modifier.matchParentSize().alpha(0f)) { innerTextField() }
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    val activeIndex = code.length.coerceAtMost(5)
                    for (i in 0 until 6) {
                        val ch = code.getOrNull(i)?.toString().orEmpty()
                        val isActiveCell = focused && (i == activeIndex)
                        Box(
                            modifier = Modifier
                                .weight(1f)
                                .heightIn(min = 60.dp)
                                .clip(TurboRadii.medium)
                                .background(c.surfaceContainerHigh)
                                .border(
                                    width = if (isActiveCell) 2.dp else 1.dp,
                                    color = if (isActiveCell) c.primary else c.outline,
                                    shape = TurboRadii.medium,
                                ),
                            contentAlignment = Alignment.Center,
                        ) {
                            if (ch.isNotEmpty()) {
                                Text(
                                    text = ch,
                                    style = TurboType.monoOtp,
                                    color = c.onSurface,
                                )
                            } else if (isActiveCell) {
                                Box(
                                    Modifier
                                        .width(2.dp)
                                        .height(24.dp)
                                        .clip(RoundedCornerShape(1.dp))
                                        .background(c.primary)
                                )
                            }
                        }
                    }
                }
            }
        },
    )
}

@Composable
fun TurboTextField(
    value: String,
    onValueChange: (String) -> Unit,
    hint: String,
    modifier: Modifier = Modifier,
    keyboardType: KeyboardType = KeyboardType.Text,
    singleLine: Boolean = true,
    tag: String = "",
) {
    val c = LocalTurboColors.current
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = modifier
            .fillMaxWidth()
            .then(if (tag.isNotBlank()) Modifier.testTag(tag) else Modifier),
        placeholder = { Text(hint, color = c.muted, style = MaterialTheme.typography.bodyMedium) },
        singleLine = singleLine,
        textStyle = MaterialTheme.typography.bodyLarge.copy(color = c.onSurface),
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        shape = TurboRadii.medium,
        colors = OutlinedTextFieldDefaults.colors(
            focusedContainerColor = c.surfaceContainerHigh,
            unfocusedContainerColor = c.surfaceContainerHigh,
            focusedBorderColor = c.primary,
            unfocusedBorderColor = c.outline,
            focusedTextColor = c.onSurface,
            unfocusedTextColor = c.onSurface,
            cursorColor = c.primary,
        ),
    )
}

@Composable
fun GroupedListCard(
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val c = LocalTurboColors.current
    Column(
        modifier = modifier
            .fillMaxWidth()
            .clip(TurboRadii.large)
            .background(c.surfaceContainer),
    ) {
        content()
    }
}

@Composable
fun InsetDivider() {
    HorizontalDivider(
        modifier = Modifier.padding(start = TurboSpacing.dividerInset),
        thickness = 1.dp,
        color = LocalTurboColors.current.outlineVariant,
    )
}

@Composable
fun SettingsListRow(
    icon: ImageVector,
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    valueText: String? = null,
    valueColor: Color = LocalTurboColors.current.onSurfaceVariant,
    showChevron: Boolean = false,
    onClick: (() -> Unit)? = null,
) {
    val c = LocalTurboColors.current
    val clickableMod = if (onClick != null) {
        Modifier.clickable(role = Role.Button, onClick = onClick)
    } else {
        Modifier
    }
    Row(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = if (subtitle != null) TurboSpacing.rowTwoLine else TurboSpacing.touchMin)
            .then(clickableMod)
            .padding(horizontal = TurboSpacing.gutter, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = c.onSurfaceVariant,
            modifier = Modifier.size(22.dp),
        )
        Spacer(Modifier.width(18.dp))
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(end = 12.dp),
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.labelLarge,
                color = c.onSurface,
            )
            if (!subtitle.isNullOrBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = c.muted,
                )
            }
        }
        if (!valueText.isNullOrBlank() || showChevron) {
            Row(
                modifier = Modifier.widthIn(min = if (!valueText.isNullOrBlank()) 56.dp else 20.dp, max = 140.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.End,
            ) {
                if (!valueText.isNullOrBlank()) {
                    Text(
                        text = valueText,
                        style = MaterialTheme.typography.bodySmall.copy(fontWeight = FontWeight.Medium),
                        color = valueColor,
                        textAlign = TextAlign.End,
                        modifier = Modifier.widthIn(max = if (showChevron) 118.dp else 140.dp),
                    )
                }
                if (showChevron) {
                    if (!valueText.isNullOrBlank()) Spacer(Modifier.width(4.dp))
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

@Composable
fun SettingsToggleRow(
    icon: ImageVector,
    title: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
) {
    val c = LocalTurboColors.current
    Row(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = if (subtitle != null) TurboSpacing.rowTwoLine else TurboSpacing.rowOneLine)
            .toggleable(
                value = checked,
                role = Role.Switch,
                onValueChange = onCheckedChange,
            )
            .padding(horizontal = TurboSpacing.gutter, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(
            imageVector = icon,
            contentDescription = null,
            tint = c.onSurfaceVariant,
            modifier = Modifier.size(22.dp),
        )
        Spacer(Modifier.width(18.dp))
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(end = 12.dp),
        ) {
            Text(
                text = title,
                style = MaterialTheme.typography.labelLarge,
                color = c.onSurface,
            )
            if (!subtitle.isNullOrBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = c.muted,
                )
            }
        }
        Switch(
            checked = checked,
            onCheckedChange = null, // handled by row toggleable for full 48dp+ hit target
            colors = SwitchDefaults.colors(
                checkedThumbColor = c.onPrimary,
                checkedTrackColor = c.primary,
                checkedBorderColor = c.primary,
                uncheckedThumbColor = c.outline,
                uncheckedTrackColor = c.surfaceContainerHighest,
                uncheckedBorderColor = c.outline,
            ),
        )
    }
}

@Composable
fun TurboNavBar(
    active: Tab,
    pendingCount: Int,
    onSelect: (Tab) -> Unit,
) {
    val c = LocalTurboColors.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .background(c.surfaceContainer)
            .navigationBarsPadding()
            .padding(vertical = 6.dp),
    ) {
        Tab.entries.forEach { t ->
            val selected = t == active
            Column(
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 56.dp)
                    .testTag("tab_${t.name}")
                    .selectable(
                        selected = selected,
                        role = Role.Tab,
                        onClick = { onSelect(t) },
                    ),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center,
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Box(
                        modifier = Modifier
                            .size(width = 56.dp, height = 32.dp)
                            .clip(TurboRadii.full)
                            .background(if (selected) c.primaryContainer else Color.Transparent),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(
                            imageVector = t.icon(selected),
                            contentDescription = null,
                            tint = if (selected) c.onPrimaryContainer else c.onSurfaceVariant,
                            modifier = Modifier.size(24.dp),
                        )
                    }
                    if (t == Tab.APPROVALS && pendingCount > 0) {
                        Box(
                            modifier = Modifier
                                .align(Alignment.TopEnd)
                                .padding(end = 6.dp)
                                .defaultMinSize(minWidth = 16.dp, minHeight = 16.dp)
                                .clip(TurboRadii.full)
                                .background(c.warn)
                                .padding(horizontal = 4.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                text = pendingCount.toString(),
                                color = c.onWarn,
                                fontSize = 11.sp,
                                lineHeight = 14.sp,
                                fontFamily = BeVietnamPro,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    text = stringResource(t.label),
                    style = MaterialTheme.typography.labelMedium.copy(
                        fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium,
                    ),
                    color = if (selected) c.onSurface else c.onSurfaceVariant,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}
