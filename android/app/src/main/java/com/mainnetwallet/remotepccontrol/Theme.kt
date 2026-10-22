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

/** Fixed colours that are not part of the Material scheme (status colours, trackpad border). */
object Palette {
    val Outline = Color(0xFF2A3342)
    val Good = Color(0xFF5FD3A0)
    val Warn = Color(0xFFF2C14E)
    val Bad = Color(0xFFFF6B6B)
}

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8AB4FF),
    onPrimary = Color(0xFF00255A),
    primaryContainer = Color(0xFF1D3A6B),
    onPrimaryContainer = Color(0xFFD6E4FF),
    secondary = Color(0xFFB4C5E4),
    onSecondary = Color(0xFF1B2B45),
    secondaryContainer = Color(0xFF263248),
    onSecondaryContainer = Color(0xFFDCE6FA),
    background = Color(0xFF0B0E14),
    onBackground = Color(0xFFE6EAF2),
    surface = Color(0xFF131822),
    onSurface = Color(0xFFE6EAF2),
    surfaceVariant = Color(0xFF1B2230),
    onSurfaceVariant = Color(0xFF9AA6BA),
    outline = Color(0xFF3A4558),
    outlineVariant = Palette.Outline,
    error = Color(0xFFFF6B6B),
    onError = Color(0xFF4A0008),
    errorContainer = Color(0xFF5C1A1F),
    onErrorContainer = Color(0xFFFFDAD9)
)

private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(6.dp),
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(14.dp),
    large = RoundedCornerShape(20.dp),
    extraLarge = RoundedCornerShape(28.dp)
)

private val AppTypography = Typography().let { base ->
    base.copy(
        headlineMedium = base.headlineMedium.copy(fontWeight = FontWeight.SemiBold),
        headlineSmall = base.headlineSmall.copy(fontWeight = FontWeight.SemiBold),
        titleLarge = base.titleLarge.copy(fontWeight = FontWeight.SemiBold),
        titleMedium = base.titleMedium.copy(fontWeight = FontWeight.SemiBold)
    )
}

/** The app is dark-only, whatever the system theme is. */
@Composable
fun RemotePcTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = DarkColors, shapes = AppShapes, typography = AppTypography, content = content)
}
