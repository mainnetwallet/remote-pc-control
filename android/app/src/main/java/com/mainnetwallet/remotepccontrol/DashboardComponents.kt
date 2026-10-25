package com.mainnetwallet.remotepccontrol

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.LocalIndication
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/*
 * Dashboard-only building blocks. They are used by DashboardScreen.kt and nowhere else, so the shared
 * Theme.kt / Components.kt (used by the connect and session screens) stay exactly as they were.
 */

/** Colours that only the dashboard needs. Status colours (green / amber / red) come from [Palette]. */
internal object DashColors {
    val BgTop = Color(0xFF0F1B33)
    val BgBottom = Color(0xFF080B11)
    val PanelTop = Color(0xFF18202E)
    val PanelBottom = Color(0xFF121722)
    val PanelBorder = Color(0xFF263044)
    val HeroTop = Color(0xFF1B2D50)
    val HeroBottom = Color(0xFF111A2C)
    val HeroBorder = Color(0xFF2F4672)
    val Blue = Color(0xFF8AB4FF)
    val Violet = Color(0xFFB7A3FF)
}

// ---------------------------------------------------------------------------------------------
// Icons, drawn on a 24 x 24 grid so no icon dependency is needed.
// ---------------------------------------------------------------------------------------------

internal enum class Glyph { MONITOR, LOCK, MOON, RESTART, POWER, DOWN, UP, LOGOUT, CLOCK, CHECK, PLAY }

@Composable
internal fun DashIcon(glyph: Glyph, tint: Color, modifier: Modifier = Modifier, iconSize: Dp = 22.dp) {
    Canvas(modifier.size(iconSize)) {
        val u = size.width / 24f
        val stroke = Stroke(width = 2f * u, cap = StrokeCap.Round, join = StrokeJoin.Round)
        fun pt(x: Float, y: Float) = Offset(x * u, y * u)
        fun line(x1: Float, y1: Float, x2: Float, y2: Float) {
            drawLine(tint, pt(x1, y1), pt(x2, y2), strokeWidth = 2f * u, cap = StrokeCap.Round)
        }
        when (glyph) {
            Glyph.MONITOR -> {
                drawRoundRect(
                    tint, topLeft = pt(3f, 4f), size = Size(18f * u, 12f * u),
                    cornerRadius = CornerRadius(2.5f * u, 2.5f * u), style = stroke
                )
                line(8f, 20f, 16f, 20f)
                line(12f, 16f, 12f, 20f)
            }
            Glyph.LOCK -> {
                drawRoundRect(
                    tint, topLeft = pt(5f, 11f), size = Size(14f * u, 10f * u),
                    cornerRadius = CornerRadius(2.5f * u, 2.5f * u), style = stroke
                )
                drawArc(tint, 180f, 180f, false, topLeft = pt(8f, 4f), size = Size(8f * u, 8f * u), style = stroke)
                line(8f, 8f, 8f, 11f)
                line(16f, 8f, 16f, 11f)
            }
            Glyph.MOON -> {
                val moon = Path().apply {
                    arcTo(Rect(pt(3f, 3f), Size(18f * u, 18f * u)), 5f, 260f, true)
                    arcTo(Rect(pt(9.18f, 0.98f), Size(13.84f * u, 13.84f * u)), 225f, -180f, false)
                    close()
                }
                drawPath(moon, tint, style = stroke)
            }
            Glyph.RESTART -> {
                drawArc(tint, 20f, 300f, false, topLeft = pt(4f, 4f), size = Size(16f * u, 16f * u), style = stroke)
                // Arrow head at the end of the arc (320 degrees), pointing along the clockwise tangent.
                val a = 320.0 * PI / 180.0
                val ex = 12f + 8f * cos(a).toFloat()
                val ey = 12f + 8f * sin(a).toFloat()
                val tx = -sin(a).toFloat()
                val ty = cos(a).toFloat()
                val nx = cos(a).toFloat()
                val ny = sin(a).toFloat()
                val tipX = ex + tx * 1.5f
                val tipY = ey + ty * 1.5f
                line(tipX, tipY, tipX - tx * 4f + nx * 3.5f, tipY - ty * 4f + ny * 3.5f)
                line(tipX, tipY, tipX - tx * 4f - nx * 3.5f, tipY - ty * 4f - ny * 3.5f)
            }
            Glyph.POWER -> {
                drawArc(tint, -60f, 300f, false, topLeft = pt(5f, 6f), size = Size(14f * u, 14f * u), style = stroke)
                line(12f, 3f, 12f, 12f)
            }
            Glyph.DOWN -> {
                line(12f, 5f, 12f, 19f)
                line(6f, 13f, 12f, 19f)
                line(18f, 13f, 12f, 19f)
            }
            Glyph.UP -> {
                line(12f, 19f, 12f, 5f)
                line(6f, 11f, 12f, 5f)
                line(18f, 11f, 12f, 5f)
            }
            Glyph.LOGOUT -> {
                line(10f, 4f, 5f, 4f)
                line(5f, 4f, 5f, 20f)
                line(5f, 20f, 10f, 20f)
                line(10f, 12f, 20f, 12f)
                line(16f, 8f, 20f, 12f)
                line(16f, 16f, 20f, 12f)
            }
            Glyph.CLOCK -> {
                drawCircle(tint, radius = 9f * u, center = pt(12f, 12f), style = stroke)
                line(12f, 7f, 12f, 12f)
                line(12f, 12f, 16f, 14f)
            }
            Glyph.CHECK -> {
                line(5f, 12.5f, 10f, 17.5f)
                line(10f, 17.5f, 19f, 7f)
            }
            Glyph.PLAY -> {
                val tri = Path().apply {
                    moveTo(8f * u, 5f * u)
                    lineTo(19f * u, 12f * u)
                    lineTo(8f * u, 19f * u)
                    close()
                }
                drawPath(tri, tint)
                drawPath(tri, tint, style = stroke)
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Layout primitives
// ---------------------------------------------------------------------------------------------

/** Layered charcoal panel with a faint top-to-bottom gradient and a hairline border. */
@Composable
internal fun DashPanel(modifier: Modifier = Modifier, padding: Dp = 16.dp, content: @Composable ColumnScope.() -> Unit) {
    val shape = RoundedCornerShape(22.dp)
    Column(
        modifier
            .clip(shape)
            .background(Brush.verticalGradient(listOf(DashColors.PanelTop, DashColors.PanelBottom)))
            .border(1.dp, DashColors.PanelBorder, shape)
            .padding(padding),
        content = content
    )
}

/** A titled group of content, with an optional short note on the right ("Live", "Waiting for data"). */
@Composable
internal fun DashSection(title: String, trailing: String? = null, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            if (trailing != null) Text(
                trailing, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1, overflow = TextOverflow.Ellipsis
            )
        }
        content()
    }
}

// ---------------------------------------------------------------------------------------------
// Header and status
// ---------------------------------------------------------------------------------------------

@Composable
private fun DashPulseDot(color: Color) {
    val transition = rememberInfiniteTransition(label = "pulse")
    val phase by transition.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(animation = tween(durationMillis = 1800, easing = LinearEasing), repeatMode = RepeatMode.Restart),
        label = "pulsePhase"
    )
    Canvas(Modifier.size(16.dp)) {
        val r = 4.dp.toPx()
        drawCircle(color, radius = r, center = center)
        drawCircle(color.copy(alpha = 0.45f * (1f - phase)), radius = r + r * phase, center = center)
    }
}

@Composable
private fun DashDot(color: Color, pulsing: Boolean) {
    if (pulsing) DashPulseDot(color)
    else Box(Modifier.size(16.dp), contentAlignment = Alignment.Center) { Box(Modifier.size(8.dp).background(color, CircleShape)) }
}

/** Rounded status badge: a dot (pulsing while live) and a word. The colour is never the only signal. */
@Composable
internal fun DashStatusPill(text: String, color: Color, pulsing: Boolean) {
    val shape = RoundedCornerShape(50)
    Row(
        Modifier
            .clip(shape)
            .background(color.copy(alpha = 0.14f))
            .border(1.dp, color.copy(alpha = 0.40f), shape)
            .padding(start = 6.dp, end = 12.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        DashDot(color, pulsing)
        Spacer(Modifier.width(4.dp))
        Text(text, style = MaterialTheme.typography.labelMedium, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
internal fun DashHeader(hostname: String, reachable: Boolean, uptime: String, onLogout: () -> Unit) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(28.dp)
    val tileShape = RoundedCornerShape(16.dp)
    Column(
        Modifier
            .fillMaxWidth()
            .clip(shape)
            .background(Brush.linearGradient(listOf(DashColors.HeroTop, DashColors.HeroBottom)))
            .border(1.dp, DashColors.HeroBorder, shape)
            .padding(16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(52.dp).clip(tileShape)
                    .background(cs.primary.copy(alpha = 0.16f))
                    .border(1.dp, cs.primary.copy(alpha = 0.35f), tileShape),
                contentAlignment = Alignment.Center
            ) { DashIcon(Glyph.MONITOR, cs.primary, iconSize = 28.dp) }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(hostname, style = MaterialTheme.typography.titleLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(6.dp))
                DashStatusPill(if (reachable) "Connected" else "Offline, retrying", if (reachable) Palette.Good else Palette.Bad, reachable)
            }
            Spacer(Modifier.width(8.dp))
            Box(
                Modifier.size(48.dp).clip(CircleShape)
                    .background(Color.White.copy(alpha = 0.06f))
                    .clickable(onClickLabel = "Log out", role = Role.Button, onClick = onLogout)
                    .semantics { contentDescription = "Log out" },
                contentAlignment = Alignment.Center
            ) { DashIcon(Glyph.LOGOUT, cs.onSurfaceVariant, iconSize = 22.dp) }
        }
        Spacer(Modifier.height(14.dp))
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Color.Black.copy(alpha = 0.22f))
                .padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            DashIcon(Glyph.CLOCK, cs.onSurfaceVariant, iconSize = 16.dp)
            Spacer(Modifier.width(8.dp))
            Text(uptime, style = MaterialTheme.typography.bodyMedium, color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

// ---------------------------------------------------------------------------------------------
// System gauges
// ---------------------------------------------------------------------------------------------

@Composable
private fun DashRing(percent: Int?, color: Color, ringSize: Dp) {
    val cs = MaterialTheme.colorScheme
    val fraction by animateFloatAsState(
        targetValue = (percent ?: 0).coerceIn(0, 100) / 100f,
        animationSpec = tween(durationMillis = 700),
        label = "gauge"
    )
    val numberStyle = (if (ringSize >= 76.dp) MaterialTheme.typography.titleLarge else MaterialTheme.typography.titleMedium)
        .copy(fontFeatureSettings = "tnum")
    Box(Modifier.size(ringSize), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = 8.dp.toPx()
            val topLeft = Offset(stroke / 2, stroke / 2)
            val arc = Size(size.width - stroke, size.height - stroke)
            drawArc(Color.White.copy(alpha = 0.07f), 0f, 360f, false, topLeft = topLeft, size = arc, style = Stroke(width = stroke))
            if (fraction > 0f) drawArc(
                color, -90f, 360f * fraction, false, topLeft = topLeft, size = arc,
                style = Stroke(width = stroke, cap = StrokeCap.Round)
            )
        }
        Row(verticalAlignment = Alignment.Bottom) {
            Text(if (percent == null) "–" else "$percent", style = numberStyle, maxLines = 1)
            if (percent != null) Text(
                "%", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant,
                modifier = Modifier.padding(bottom = 3.dp)
            )
        }
    }
}

/** One resource card: ring with the percentage, the name, used / total, and a word for the load level. */
@Composable
internal fun DashGauge(label: String, percent: Int?, detail: String, ringSize: Dp, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    val color = when {
        percent == null -> cs.onSurfaceVariant
        percent >= 90 -> Palette.Bad
        percent >= 70 -> Palette.Warn
        else -> cs.primary
    }
    val level = when {
        percent == null -> "No data"
        percent >= 90 -> "Critical"
        percent >= 70 -> "High"
        else -> "Normal"
    }
    DashPanel(modifier, padding = 12.dp) {
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            DashRing(percent, color, ringSize)
            Spacer(Modifier.height(10.dp))
            Text(label, style = MaterialTheme.typography.titleSmall, maxLines = 1)
            Spacer(Modifier.height(2.dp))
            Text(
                detail, style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant,
                textAlign = TextAlign.Center, minLines = 2, maxLines = 2, overflow = TextOverflow.Ellipsis
            )
            Spacer(Modifier.height(6.dp))
            Text(level, style = MaterialTheme.typography.labelMedium, color = color, maxLines = 1)
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Network
// ---------------------------------------------------------------------------------------------

@Composable
internal fun DashRateTile(label: String, bytesPerSec: Long?, glyph: Glyph, tint: Color, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(16.dp)
    val text = bytesPerSec?.let { formatBytes(it) }
    val number = text?.substringBefore(' ') ?: "–"
    val unit = if (text == null) "" else text.substringAfter(' ') + "/s"
    Column(
        modifier
            .clip(shape)
            .background(tint.copy(alpha = 0.10f))
            .border(1.dp, tint.copy(alpha = 0.28f), shape)
            .padding(12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(28.dp).clip(CircleShape).background(tint.copy(alpha = 0.20f)), contentAlignment = Alignment.Center) {
                DashIcon(glyph, tint, iconSize = 16.dp)
            }
            Spacer(Modifier.width(8.dp))
            Text(label, style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Spacer(Modifier.height(10.dp))
        Row(verticalAlignment = Alignment.Bottom) {
            Text(number, style = MaterialTheme.typography.titleLarge.copy(fontFeatureSettings = "tnum"), maxLines = 1)
            Spacer(Modifier.width(4.dp))
            Text(
                unit, style = MaterialTheme.typography.labelMedium, color = cs.onSurfaceVariant, maxLines = 1,
                modifier = Modifier.padding(bottom = 3.dp)
            )
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Power
// ---------------------------------------------------------------------------------------------

/** Touch tile for one power action. Destructive actions get a stronger tint and a heavier border. */
@Composable
internal fun DashPowerTile(
    label: String, caption: String, glyph: Glyph, tint: Color, destructive: Boolean,
    onClick: () -> Unit, modifier: Modifier = Modifier
) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(20.dp)
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(targetValue = if (pressed) 0.96f else 1f, animationSpec = tween(durationMillis = 120), label = "press")
    Column(
        modifier
            .scale(scale)
            .clip(shape)
            .background(DashColors.PanelBottom)
            .background(tint.copy(alpha = if (destructive) 0.16f else 0.10f))
            .border(if (destructive) 1.5.dp else 1.dp, tint.copy(alpha = if (destructive) 0.60f else 0.28f), shape)
            .clickable(interactionSource = interaction, indication = LocalIndication.current, role = Role.Button, onClick = onClick)
            .padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Box(Modifier.size(40.dp).clip(CircleShape).background(tint.copy(alpha = 0.20f)), contentAlignment = Alignment.Center) {
            DashIcon(glyph, tint, iconSize = 22.dp)
        }
        Column {
            Text(label, style = MaterialTheme.typography.titleMedium, color = if (destructive) tint else cs.onSurface, maxLines = 1)
            Text(caption, style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant, maxLines = 1)
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Live screen quality
// ---------------------------------------------------------------------------------------------

@Composable
private fun DashQualityChip(q: Quality, on: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val cs = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(14.dp)
    Column(
        modifier
            .heightIn(min = 56.dp)
            .clip(shape)
            .background(if (on) cs.primary.copy(alpha = 0.18f) else Color.White.copy(alpha = 0.04f))
            .border(if (on) 1.5.dp else 1.dp, if (on) cs.primary else DashColors.PanelBorder, shape)
            .selectable(selected = on, role = Role.RadioButton, onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.Center
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                q.label, style = MaterialTheme.typography.labelLarge, color = if (on) cs.primary else cs.onSurface,
                maxLines = 2, modifier = Modifier.weight(1f, fill = false)
            )
            if (on) {
                Spacer(Modifier.width(4.dp))
                DashIcon(Glyph.CHECK, cs.primary, iconSize = 14.dp)
            }
        }
        Text(q.fps.toString() + " fps", style = MaterialTheme.typography.labelSmall, color = cs.onSurfaceVariant, maxLines = 1)
    }
}

/**
 * All six quality presets as selectable chips: three per row, or two when the card is narrow, so no
 * label is ever squeezed. Selection goes straight to [onSelect] with the original [Quality] value.
 */
@Composable
internal fun DashQualityGrid(selected: Quality, onSelect: (Quality) -> Unit, modifier: Modifier = Modifier) {
    BoxWithConstraints(modifier.fillMaxWidth()) {
        val columns = if (maxWidth < 280.dp) 2 else 3
        Column(Modifier.selectableGroup(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Quality.values().toList().chunked(columns).forEach { rowItems ->
                Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    rowItems.forEach { q ->
                        DashQualityChip(q, q == selected, { onSelect(q) }, Modifier.weight(1f).fillMaxHeight())
                    }
                    repeat(columns - rowItems.size) { Spacer(Modifier.weight(1f)) }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Notices
// ---------------------------------------------------------------------------------------------

@Composable
internal fun DashNotice(text: String, isError: Boolean) {
    val color = if (isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary
    val shape = RoundedCornerShape(14.dp)
    Text(
        text,
        Modifier.fillMaxWidth().clip(shape).background(color.copy(alpha = 0.12f)).border(1.dp, color.copy(alpha = 0.30f), shape).padding(12.dp),
        style = MaterialTheme.typography.bodySmall, color = color, textAlign = TextAlign.Center
    )
}
