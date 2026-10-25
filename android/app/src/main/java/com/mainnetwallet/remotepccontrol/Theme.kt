package com.mainnetwallet.remotepccontrol

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Fixed colours that are not part of the Material scheme (status colours, trackpad border). */
object Palette {
    // Status colors - refined for premium feel
    val Success = Color(0xFF34D399)   // Emerald green for connected/good
    val Warning = Color(0xFFFBBF24)   // Amber for warnings
    val Danger = Color(0xFFF87171)    // Soft red for critical/destructive
    val Info = Color(0xFF60A5FA)      // Sky blue for informational

    // Accent colors for interactive elements
    val AccentBlue = Color(0xFF3B82F6)
    val AccentBlueContainer = Color(0xFF1E3A5F)
    val AccentGreen = Color(0xFF22C55E)
    val AccentRed = Color(0xFFEF4444)

    // Subtle border (Trackpad.kt draws its border with Palette.Outline)
    val Outline = Color(0xFF2A3342)
    val Hairline = Color(0xFF2A3342)
    val BorderSubtle = Color(0xFF334155)
    val BorderFocus = Color(0xFF475569)

    // Overlay scrims
    val ScrimLight = Color(0x1AFFFFFF)
    val ScrimMedium = Color(0x33FFFFFF)
}

/** Design tokens for spacing, sizing, and motion */
object DesignTokens {
    // Spacing scale (4dp base)
    val SpaceXS = 4.dp
    val SpaceSM = 8.dp
    val SpaceMD = 12.dp
    val SpaceLG = 16.dp
    val SpaceXL = 20.dp
    val Space2XL = 24.dp
    val Space3XL = 32.dp

    // Border radius
    val RadiusXS = 6.dp
    val RadiusSM = 10.dp
    val RadiusMD = 14.dp
    val RadiusLG = 18.dp
    val RadiusXL = 24.dp
    val RadiusPill = 999.dp

    // Touch targets
    val TouchTargetMin = 44.dp
    val TouchTargetComfortable = 48.dp
    val TouchTargetLarge = 52.dp

    // Gauge sizing
    val GaugeSize = 76.dp
    val GaugeStroke = 7.dp

    // Animation durations
    val DurationFast = 150
    val DurationNormal = 250
    val DurationSlow = 350

    // Typography scale
    val FontSizeXS = 11.sp
    val FontSizeSM = 13.sp
    val FontSizeMD = 15.sp
    val FontSizeLG = 17.sp
    val FontSizeXL = 20.sp
    val FontSize2XL = 24.sp
    val FontSize3XL = 28.sp

    // Font weights
    val WeightRegular = FontWeight.Normal
    val WeightMedium = FontWeight.Medium
    val WeightSemiBold = FontWeight.SemiBold
    val WeightBold = FontWeight.Bold
}

private val DarkColors = darkColorScheme(
    // Primary - Refined blue for primary actions
    primary = Color(0xFF60A5FA),
    onPrimary = Color(0xFF001E3A),
    primaryContainer = Color(0xFF1E3A5F),
    onPrimaryContainer = Color(0xFFD6E4FF),

    // Secondary - Muted blue-gray for secondary actions
    secondary = Color(0xFF94A3B8),
    onSecondary = Color(0xFF1E293B),
    secondaryContainer = Color(0xFF334155),
    onSecondaryContainer = Color(0xFFE2E8F0),

    // Tertiary - For accent highlights
    tertiary = Color(0xFF34D399),
    onTertiary = Color(0xFF064E3B),
    tertiaryContainer = Color(0xFF065F46),
    onTertiaryContainer = Color(0xFFD1FAE5),

    // Surface hierarchy - Deep, layered dark surfaces
    background = Color(0xFF080C12),       // Near-black app background
    onBackground = Color(0xFFF1F5F9),
    surface = Color(0xFF0F141E),          // Primary card surface
    onSurface = Color(0xFFF1F5F9),
    surfaceVariant = Color(0xFF171D2A),   // Elevated/alternate surface
    onSurfaceVariant = Color(0xFF94A3B8),
    surfaceContainer = Color(0xFF111722), // Slightly elevated
    surfaceContainerLow = Color(0xFF0D121B),
    surfaceContainerHigh = Color(0xFF1E293B),
    surfaceContainerHighest = Color(0xFF273347),

    // Outline - Subtle borders
    outline = Color(0xFF334155),
    outlineVariant = Color(0xFF1E293B),

    // Error - Destructive actions
    error = Color(0xFFF87171),
    onError = Color(0xFF450A0A),
    errorContainer = Color(0xFF7F1D1D),
    onErrorContainer = Color(0xFFFEE2E2),

    // Inverse (for modals over content)
    inverseSurface = Color(0xFFF1F5F9),
    inverseOnSurface = Color(0xFF080C12),

    // Scrim
    scrim = Color(0xFF000000)
)

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(DesignTokens.RadiusXS),
    small = RoundedCornerShape(DesignTokens.RadiusSM),
    medium = RoundedCornerShape(DesignTokens.RadiusMD),
    large = RoundedCornerShape(DesignTokens.RadiusLG),
    extraLarge = RoundedCornerShape(DesignTokens.RadiusXL)
)

private val AppTypography = Typography().let { base ->
    base.copy(
        // Display
        displayLarge = base.displayLarge.copy(
            fontSize = DesignTokens.FontSize3XL,
            fontWeight = DesignTokens.WeightSemiBold,
            letterSpacing = -0.5.sp
        ),
        displayMedium = base.displayMedium.copy(
            fontSize = DesignTokens.FontSize2XL,
            fontWeight = DesignTokens.WeightSemiBold,
            letterSpacing = -0.3.sp
        ),
        displaySmall = base.displaySmall.copy(
            fontSize = DesignTokens.FontSizeXL,
            fontWeight = DesignTokens.WeightSemiBold,
            letterSpacing = -0.2.sp
        ),

        // Headline
        headlineLarge = base.headlineLarge.copy(
            fontSize = DesignTokens.FontSize2XL,
            fontWeight = DesignTokens.WeightSemiBold,
            letterSpacing = -0.3.sp
        ),
        headlineMedium = base.headlineMedium.copy(
            fontSize = DesignTokens.FontSizeXL,
            fontWeight = DesignTokens.WeightSemiBold,
            letterSpacing = -0.2.sp
        ),
        headlineSmall = base.headlineSmall.copy(
            fontSize = DesignTokens.FontSizeLG,
            fontWeight = DesignTokens.WeightSemiBold,
            letterSpacing = -0.1.sp
        ),

        // Title
        titleLarge = base.titleLarge.copy(
            fontSize = DesignTokens.FontSizeLG,
            fontWeight = DesignTokens.WeightSemiBold
        ),
        titleMedium = base.titleMedium.copy(
            fontSize = DesignTokens.FontSizeMD,
            fontWeight = DesignTokens.WeightSemiBold
        ),
        titleSmall = base.titleSmall.copy(
            fontSize = DesignTokens.FontSizeSM,
            fontWeight = DesignTokens.WeightMedium
        ),

        // Body
        bodyLarge = base.bodyLarge.copy(
            fontSize = DesignTokens.FontSizeLG,
            lineHeight = 24.sp
        ),
        bodyMedium = base.bodyMedium.copy(
            fontSize = DesignTokens.FontSizeMD,
            lineHeight = 22.sp
        ),
        bodySmall = base.bodySmall.copy(
            fontSize = DesignTokens.FontSizeSM,
            lineHeight = 20.sp
        ),

        // Label
        labelLarge = base.labelLarge.copy(
            fontSize = DesignTokens.FontSizeSM,
            fontWeight = DesignTokens.WeightMedium,
            letterSpacing = 0.1.sp
        ),
        labelMedium = base.labelMedium.copy(
            fontSize = DesignTokens.FontSizeXS,
            fontWeight = DesignTokens.WeightMedium,
            letterSpacing = 0.3.sp
        ),
        labelSmall = base.labelSmall.copy(
            fontSize = DesignTokens.FontSizeXS,
            fontWeight = DesignTokens.WeightMedium,
            letterSpacing = 0.4.sp
        )
    )
}

/** The app is dark-only, whatever the system theme is. */
@Composable
fun RemotePcTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColors,
        shapes = AppShapes,
        typography = AppTypography,
        content = content
    )
}