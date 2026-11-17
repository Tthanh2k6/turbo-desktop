package dev.turbodesktop.remote

import android.app.Activity
import android.provider.Settings
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

val BeVietnamPro = FontFamily(
    Font(R.font.be_vietnam_pro_regular, FontWeight.Normal),
    Font(R.font.be_vietnam_pro_medium, FontWeight.Medium),
    Font(R.font.be_vietnam_pro_semibold, FontWeight.SemiBold),
    Font(R.font.be_vietnam_pro_bold, FontWeight.Bold),
)

val JetBrainsMono = FontFamily(
    Font(R.font.jetbrains_mono, FontWeight.Normal),
    Font(R.font.jetbrains_mono, FontWeight.Medium),
    Font(R.font.jetbrains_mono, FontWeight.SemiBold),
    Font(R.font.jetbrains_mono, FontWeight.Bold),
)

@Immutable
data class TurboColors(
    val bg: Color = Color(0xFF0F1114),
    val surfaceContainerLow: Color = Color(0xFF16191D),
    val surfaceContainer: Color = Color(0xFF1C2025),
    val surfaceContainerHigh: Color = Color(0xFF242930),
    val surfaceContainerHighest: Color = Color(0xFF2D333B),
    val onSurface: Color = Color(0xFFECEAE4),
    val onSurfaceVariant: Color = Color(0xFFA9B0BA),
    val muted: Color = Color(0xFF8C95A0),
    val outline: Color = Color(0xFF6B737E),
    val outlineVariant: Color = Color(0xFF2E343C),
    val primary: Color = Color(0xFF5CD6B0),
    val onPrimary: Color = Color(0xFF04281F),
    val primaryContainer: Color = Color(0xFF123A30),
    val onPrimaryContainer: Color = Color(0xFF9FF0D4),
    val ai: Color = Color(0xFFE0461D),
    val aiText: Color = Color(0xFFFF8A5C),
    val onAi: Color = Color(0xFF1A0702),
    val aiContainer: Color = Color(0xFF3A1A10),
    val onAiContainer: Color = Color(0xFFFFB59C),
    val stop: Color = Color(0xFFFF5468),
    val onStop: Color = Color(0xFF2B0508),
    val stopText: Color = Color(0xFFFF7A86),
    val stopContainer: Color = Color(0xFF3D1419),
    val onStopContainer: Color = Color(0xFFFFB3BA),
    val warn: Color = Color(0xFFF2B84B),
    val onWarn: Color = Color(0xFF2A1B00),
    val warnContainer: Color = Color(0xFF3A2C0E),
    val onWarnContainer: Color = Color(0xFFFFD98A),
    val inverse: Color = Color(0xFFECEAE4),
    val onInverse: Color = Color(0xFF0F1114),
    val scrim: Color = Color(0x8C000000),
    val viewfinderBg: Color = Color(0xFF07080A),
    val cropBg: Color = Color(0xFF0A0C0E),
    val chartBar: Color = Color(0xFF3E8F78),
    val playerPillBg: Color = Color(0xA6000000),
    val playerScrimTop: Color = Color(0xB3000000),
    val playerScrimBottom: Color = Color(0xBF000000),
)

val DefaultTurboColors = TurboColors()
val LocalTurboColors = staticCompositionLocalOf { DefaultTurboColors }

private val TurboColorScheme = darkColorScheme(
    primary = DefaultTurboColors.primary,
    onPrimary = DefaultTurboColors.onPrimary,
    primaryContainer = DefaultTurboColors.primaryContainer,
    onPrimaryContainer = DefaultTurboColors.onPrimaryContainer,
    secondary = DefaultTurboColors.primary,
    onSecondary = DefaultTurboColors.onPrimary,
    secondaryContainer = DefaultTurboColors.primaryContainer,
    onSecondaryContainer = DefaultTurboColors.onPrimaryContainer,
    tertiary = DefaultTurboColors.warn,
    onTertiary = DefaultTurboColors.onWarn,
    tertiaryContainer = DefaultTurboColors.warnContainer,
    onTertiaryContainer = DefaultTurboColors.onWarnContainer,
    error = DefaultTurboColors.stop,
    onError = DefaultTurboColors.onStop,
    errorContainer = DefaultTurboColors.stopContainer,
    onErrorContainer = DefaultTurboColors.onStopContainer,
    background = DefaultTurboColors.bg,
    onBackground = DefaultTurboColors.onSurface,
    surface = DefaultTurboColors.bg,
    onSurface = DefaultTurboColors.onSurface,
    onSurfaceVariant = DefaultTurboColors.onSurfaceVariant,
    surfaceContainerLowest = DefaultTurboColors.bg,
    surfaceContainerLow = DefaultTurboColors.surfaceContainerLow,
    surfaceContainer = DefaultTurboColors.surfaceContainer,
    surfaceContainerHigh = DefaultTurboColors.surfaceContainerHigh,
    surfaceContainerHighest = DefaultTurboColors.surfaceContainerHighest,
    outline = DefaultTurboColors.outline,
    outlineVariant = DefaultTurboColors.outlineVariant,
    inverseSurface = DefaultTurboColors.inverse,
    inverseOnSurface = DefaultTurboColors.onInverse,
    scrim = Color.Black,
)

private const val TNUM = "tnum"
private const val NO_LIGA = "liga 0, calt 0"

val TurboTypography = Typography(
    headlineMedium = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.SemiBold,
        fontSize = 28.sp,
        lineHeight = 36.sp,
        fontFeatureSettings = TNUM,
    ),
    headlineSmall = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.SemiBold,
        fontSize = 24.sp,
        lineHeight = 32.sp,
        fontFeatureSettings = TNUM,
    ),
    titleLarge = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.SemiBold,
        fontSize = 20.sp,
        lineHeight = 28.sp,
        fontFeatureSettings = TNUM,
    ),
    titleMedium = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        lineHeight = 24.sp,
        fontFeatureSettings = TNUM,
    ),
    bodyLarge = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.Normal,
        fontSize = 16.sp,
        lineHeight = 24.sp,
        fontFeatureSettings = TNUM,
    ),
    bodyMedium = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        fontFeatureSettings = TNUM,
    ),
    bodySmall = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.Normal,
        fontSize = 12.sp,
        lineHeight = 16.sp,
        fontFeatureSettings = TNUM,
    ),
    labelLarge = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.Medium,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        fontFeatureSettings = TNUM,
    ),
    labelMedium = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.Medium,
        fontSize = 12.sp,
        lineHeight = 16.sp,
        fontFeatureSettings = TNUM,
    ),
)

object TurboType {
    val button = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        lineHeight = 24.sp,
        fontFeatureSettings = TNUM,
    )
    val buttonSmall = TextStyle(
        fontFamily = BeVietnamPro,
        fontWeight = FontWeight.SemiBold,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        fontFeatureSettings = TNUM,
    )
    val monoKey = TextStyle(
        fontFamily = JetBrainsMono,
        fontWeight = FontWeight.Medium,
        fontSize = 20.sp,
        lineHeight = 28.sp,
        letterSpacing = 1.sp,
        fontFeatureSettings = NO_LIGA,
    )
    val monoOtp = TextStyle(
        fontFamily = JetBrainsMono,
        fontWeight = FontWeight.Medium,
        fontSize = 24.sp,
        lineHeight = 30.sp,
        fontFeatureSettings = NO_LIGA,
    )
    val monoCode = TextStyle(
        fontFamily = JetBrainsMono,
        fontWeight = FontWeight.Medium,
        fontSize = 13.sp,
        lineHeight = 20.sp,
        fontFeatureSettings = NO_LIGA,
    )
    val monoTime = TextStyle(
        fontFamily = JetBrainsMono,
        fontWeight = FontWeight.Normal,
        fontSize = 12.sp,
        lineHeight = 16.sp,
        fontFeatureSettings = NO_LIGA,
    )
}

object TurboRadii {
    val extraSmall = RoundedCornerShape(6.dp)
    val small = RoundedCornerShape(8.dp)
    val medium = RoundedCornerShape(12.dp)
    val large = RoundedCornerShape(16.dp)
    val largeIncreased = RoundedCornerShape(20.dp)
    val extraLargeTop = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp)
    val full = CircleShape
}

val TurboShapes = Shapes(
    extraSmall = TurboRadii.extraSmall,
    small = TurboRadii.small,
    medium = TurboRadii.medium,
    large = TurboRadii.large,
    extraLarge = RoundedCornerShape(28.dp),
)

object TurboSpacing {
    val gutter = 16.dp
    val cardPadding = 16.dp
    val groupGap = 8.dp
    val itemGap = 12.dp
    val sectionGap = 24.dp
    val rowOneLine = 56.dp
    val rowTwoLine = 64.dp
    val dividerInset = 56.dp
    val touchMin = 48.dp
    val buttonPrimary = 56.dp
    val buttonSecondary = 48.dp
}

object TurboMotion {
    const val SHORT_MS = 100
    const val MEDIUM_MS = 250
    const val EXIT_MS = 200
    const val LONG_MS = 400
    const val EDGE_HALF_CYCLE_MS = 800 // 1600 ms full cycle
}

@Composable
fun rememberReducedMotion(): Boolean {
    val ctx = LocalContext.current
    return remember(ctx) {
        try {
            Settings.Global.getFloat(ctx.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
        } catch (_: Exception) {
            false
        }
    }
}

@Composable
fun TurboTheme(content: @Composable () -> Unit) {
    val view = LocalView.current
    if (!view.isInEditMode) {
        SideEffect {
            val window = (view.context as? Activity)?.window ?: return@SideEffect
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = false
                isAppearanceLightNavigationBars = false
            }
        }
    }
    CompositionLocalProvider(LocalTurboColors provides DefaultTurboColors) {
        MaterialTheme(
            colorScheme = TurboColorScheme,
            typography = TurboTypography,
            shapes = TurboShapes,
        ) {
            Box(Modifier.fillMaxSize().background(DefaultTurboColors.bg)) {
                content()
            }
        }
    }
}
