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
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
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
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.coerceIn
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/*
 * Dashboard-only building blocks. They are used by DashboardScreen.kt and nowhere else, so the shared
 * Theme.kt / Components.kt (used by the connect and session screens) stay exactly as they were.
 */

/** Colours that only the dashboard needs: deep navy surfaces, restrained blue accents, semantic status colours. */
internal object DashColors {
    val BgTop = Color(0xFF0A1630)
    val BgBottom = Color(0xFF050810)
    val PanelTop = Color(0xFF0F1B36)
    val PanelBottom = Color(0xFF0A1226)
    val PanelBorder = Color(0xFF1E3358)
    val Inner = Color(0xFF0B1429)
    val Blue = Color(0xFF3B9BFF)
    val Cyan = Color(0xFF38BDF8)
    val Violet = Color(0xFF9B6BFF)
    val Green = Color(0xFF1FD99A)
    val Amber = Color(0xFFF5A524)
    val Red = Color(0xFFF0455A)
    val Muted = Color(0xFF93A3C0)
}

// ---------------------------------------------------------------------------------------------
// Icons, drawn on a 24 x 24 grid so no icon dependency is needed.
// ---------------------------------------------------------------------------------------------

internal enum class Glyph {
    MONITOR, LOCK, MOON, RESTART, POWER, DOWN, UP, LOGOUT, CLOCK, CHECK, PLAY,
    HOME, GEAR, SHIELD, BOLT, BARS, WIFI, CPU, MEMORY, DISK, PIN, KEY
}

@Composable
internal fun DashIcon(glyph: Glyph, tint: Color, modifier: Modifier = Modifier, iconSize: Dp = 22.dp) {
    Canvas(modifier.size(iconSize)) {
        val u = size.width / 24f
        val stroke = Stroke(width = 2f * u, cap = StrokeCap.Round, join = StrokeJoin.Round)
        fun pt(x: Float, y: Float) = Offset(x * u, y * u)
        fun line(x1: Float, y1: Float, x2: Float, y2: Float) {
            drawLine(tint, pt(x1, y1), pt(x2, y2), strokeWidth = 2f * u, cap = StrokeCap.Round)
        }
        fun box(x: Float, y: Float, w: Float, h: Float, r: Float = 2.5f) {
            drawRoundRect(tint, topLeft = pt(x, y), size = Size(w * u, h * u), cornerRadius = CornerRadius(r * u, r * u), style = stroke)
        }
        when (glyph) {
            Glyph.MONITOR -> { box(3f, 4f, 18f, 12f); line(8f, 20f, 16f, 20f); line(12f, 16f, 12f, 20f) }
            Glyph.LOCK -> {
                box(5f, 11f, 14f, 10f)
                drawArc(tint, 180f, 180f, false, topLeft = pt(8f, 4f), size = Size(8f * u, 8f * u), style = stroke)
                line(8f, 8f, 8f, 11f); line(16f, 8f, 16f, 11f)
            }
            Glyph.MOON -> {
                val moon = Path().apply {
                    moveTo(20f * u, 14.5f * u)
                    cubicTo(15.5f * u, 17.5f * u, 8.5f * u, 15.5f * u, 8.5f * u, 8f * u)
                    cubicTo(8.5f * u, 6.5f * u, 8.9f * u, 5.2f * u, 9.6f * u, 4f * u)
                    cubicTo(5.8f * u, 5f * u, 3.5f * u, 8.4f * u, 4f * u, 12.2f * u)
                    cubicTo(4.6f * u, 16.8f * u, 9f * u, 20.2f * u, 13.6f * u, 19.6f * u)
                    cubicTo(16.6f * u, 19.2f * u, 19f * u, 17.2f * u, 20f * u, 14.5f * u)
                    close()
                }
                drawPath(moon, tint, style = stroke)
            }
            Glyph.RESTART -> {
                drawArc(tint, 20f, 300f, false, topLeft = pt(4f, 4f), size = Size(16f * u, 16f * u), style = stroke)
                line(20f, 3.5f, 20f, 8.5f); line(20f, 8.5f, 15f, 8.5f)
            }
            Glyph.POWER -> {
                drawArc(tint, -60f, 300f, false, topLeft = pt(5f, 6f), size = Size(14f * u, 14f * u), style = stroke)
                line(12f, 3f, 12f, 12f)
            }
            Glyph.DOWN -> { line(12f, 5f, 12f, 19f); line(6f, 13f, 12f, 19f); line(18f, 13f, 12f, 19f) }
            Glyph.UP -> { line(12f, 19f, 12f, 5f); line(6f, 11f, 12f, 5f); line(18f, 11f, 12f, 5f) }
            Glyph.LOGOUT -> {
                line(10f, 4f, 5f, 4f); line(5f, 4f, 5f, 20f); line(5f, 20f, 10f, 20f)
                line(10f, 12f, 20f, 12f); line(16f, 8f, 20f, 12f); line(16f, 16f, 20f, 12f)
            }
            Glyph.CLOCK -> { drawCircle(tint, radius = 9f * u, center = pt(12f, 12f), style = stroke); line(12f, 7f, 12f, 12f); line(12f, 12f, 16f, 14f) }
            Glyph.CHECK -> { line(5f, 12.5f, 10f, 17.5f); line(10f, 17.5f, 19f, 7f) }
            Glyph.PLAY -> {
                val tri = Path().apply { moveTo(8f * u, 5f * u); lineTo(19f * u, 12f * u); lineTo(8f * u, 19f * u); close() }
                drawPath(tri, tint); drawPath(tri, tint, style = stroke)
            }
            Glyph.HOME -> {
                val house = Path().apply {
                    moveTo(3.5f * u, 11f * u); lineTo(12f * u, 3.5f * u); lineTo(20.5f * u, 11f * u)
                    moveTo(5.5f * u, 9.5f * u); lineTo(5.5f * u, 20f * u); lineTo(18.5f * u, 20f * u); lineTo(18.5f * u, 9.5f * u)
                }
                drawPath(house, tint, style = stroke)
                box(10f, 14f, 4f, 6f, 1f)
            }
            Glyph.GEAR -> {
                drawCircle(tint, radius = 3.2f * u, center = pt(12f, 12f), style = stroke)
                drawCircle(tint, radius = 7f * u, center = pt(12f, 12f), style = stroke)
                for (i in 0 until 8) {
                    val a = Math.toRadians(i * 45.0)
                    val c = Math.cos(a).toFloat(); val s = Math.sin(a).toFloat()
                    line(12f + 7f * c, 12f + 7f * s, 12f + 9.8f * c, 12f + 9.8f * s)
                }
            }
            Glyph.SHIELD -> {
                val shield = Path().apply {
                    moveTo(12f * u, 3f * u); lineTo(19.5f * u, 6f * u); lineTo(19.5f * u, 12f * u)
                    cubicTo(19.5f * u, 16.5f * u, 16.5f * u, 19.5f * u, 12f * u, 21f * u)
                    cubicTo(7.5f * u, 19.5f * u, 4.5f * u, 16.5f * u, 4.5f * u, 12f * u)
                    lineTo(4.5f * u, 6f * u); close()
                }
                drawPath(shield, tint)
            }
            Glyph.BOLT -> {
                val bolt = Path().apply {
                    moveTo(13.5f * u, 2.5f * u); lineTo(5f * u, 13.5f * u); lineTo(11f * u, 13.5f * u)
                    lineTo(10f * u, 21.5f * u); lineTo(19f * u, 10f * u); lineTo(13f * u, 10f * u); close()
                }
                drawPath(bolt, tint)
            }
            Glyph.BARS -> {
                for ((x, top) in listOf(4f to 12f, 10f to 4f, 16f to 8f)) {
                    drawRoundRect(tint, topLeft = pt(x, top), size = Size(4f * u, (20f - top) * u), cornerRadius = CornerRadius(1.5f * u, 1.5f * u))
                }
            }
            Glyph.WIFI -> {
                for (r in listOf(5f, 9f, 13f)) {
                    drawArc(tint, 225f, 90f, false, topLeft = pt(12f - r, 19f - r), size = Size(2f * r * u, 2f * r * u), style = stroke)
                }
                drawCircle(tint, radius = 1.6f * u, center = pt(12f, 19f))
            }
            Glyph.CPU -> {
                box(6f, 6f, 12f, 12f, 2f); box(9.5f, 9.5f, 5f, 5f, 1f)
                for (p in listOf(9f, 12f, 15f)) { line(p, 3f, p, 6f); line(p, 18f, p, 21f); line(3f, p, 6f, p); line(18f, p, 21f, p) }
            }
            Glyph.MEMORY -> {
                box(2.5f, 7f, 19f, 9f, 1.5f)
                for (p in listOf(6.5f, 10f, 13.5f, 17f)) line(p, 10f, p, 13f)
                for (p in listOf(6f, 10f, 14f, 18f)) line(p, 16f, p, 19f)
            }
            Glyph.DISK -> {
                box(3.5f, 4f, 17f, 16f, 3f); line(3.5f, 14f, 20.5f, 14f); drawCircle(tint, radius = 1.2f * u, center = pt(16.5f, 17f))
            }
            Glyph.PIN -> {
                drawCircle(tint, radius = 8f * u, center = pt(12f, 12f), style = stroke)
                for (p in listOf(8.5f, 12f, 15.5f)) drawCircle(tint, radius = 1.1f * u, center = pt(p, 12f))
            }
            Glyph.KEY -> {
                drawCircle(tint, radius = 4f * u, center = pt(8f, 16f), style = stroke)
                line(11f, 13f, 20f, 4f); line(16f, 8f, 19f, 11f); line(13.5f, 10.5f, 16f, 13f)
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------
// Layout primitives
// ---------------------------------------------------------------------------------------------

/** Dark-blue card with a faint vertical gradient and a subtle blue hairline border. */
@Composable
internal fun DashPanel(modifier: Modifier = Modifier, padding: Dp = 10.dp, content: @Composable ColumnScope.() -> Unit) {
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

/** Card title: a blue icon and a heading, with optional content (pill, chip) pushed to the right. */
@Composable
internal fun DashSectionHeader(glyph: Glyph, title: String, tint: Color = DashColors.Blue, trailing: @Composable () -> Unit = {}) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        DashIcon(glyph, tint, iconSize = 22.dp)
        Spacer(Modifier.width(8.dp))
        Text(title, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium.copy(fontSize = 17.sp), maxLines = 1, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.width(8.dp))
        trailing()
    }
}

@Composable
private fun DashPulseDot(color: Color, animate: Boolean) {
    val transition = rememberInfiniteTransition(label = "pulse")
    val phase by transition.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(animation = tween(durationMillis = 1800, easing = LinearEasing), repeatMode = RepeatMode.Restart),
        label = "pulsePhase"
    )
    Canvas(Modifier.size(16.dp)) {
        val r = 4.5.dp.toPx()
        drawCircle(color, radius = r, center = center)
        if (animate) drawCircle(color.copy(alpha = 0.45f * (1f - phase)), radius = r + r * phase, center = center)
    }
}

/** Rounded status badge: a dot (pulsing while live) and a word. The colour is never the only signal. */
@Composable
internal fun DashStatusPill(text: String, color: Color, pulsing: Boolean, glyph: Glyph? = null) {
    val shape = RoundedCornerShape(50)
    Row(
        Modifier
            .clip(shape)
            .background(color.copy(alpha = 0.14f))
            .border(1.dp, color.copy(alpha = 0.40f), shape)
            .padding(start = 8.dp, end = 12.dp, top = 5.dp, bottom = 5.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        if (glyph != null) DashIcon(glyph, color, iconSize = 16.dp) else DashPulseDot(color, pulsing)
        Spacer(Modifier.width(5.dp))
        Text(text, style = MaterialTheme.typography.labelLarge, color = color, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/** Small rounded info chip (uptime, address, resolution). */
@Composable
internal fun DashChip(glyph: Glyph, text: String, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(12.dp)
    Row(
        modifier.clip(shape).background(Color.White.copy(alpha = 0.05f)).border(1.dp, DashColors.PanelBorder, shape)
            .padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        DashIcon(glyph, DashColors.Muted, iconSize = 15.dp)
        Spacer(Modifier.width(6.dp))
        Text(text, style = MaterialTheme.typography.labelMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

// ---------------------------------------------------------------------------------------------
// Connection header
// ---------------------------------------------------------------------------------------------

/** A stylised desktop monitor (device illustration, not a screenshot of the PC). */
@Composable
private fun DashMonitorIllustration(modifier: Modifier = Modifier) {
    Canvas(modifier.aspectRatio(1.35f)) {
        val w = size.width; val h = size.height
        drawCircle(Brush.radialGradient(listOf(DashColors.Blue.copy(alpha = 0.35f), Color.Transparent), center = Offset(w / 2, h * 0.45f), radius = w * 0.65f), radius = w * 0.65f, center = Offset(w / 2, h * 0.45f))
        val screenH = h * 0.74f
        drawRoundRect(Color(0xFF0B1226), Offset(w * 0.04f, 0f), Size(w * 0.92f, screenH), CornerRadius(8.dp.toPx()))
        drawRoundRect(
            Brush.linearGradient(listOf(Color(0xFF0B3C9E), Color(0xFF2D8CFF), Color(0xFF123A8C)), start = Offset(0f, 0f), end = Offset(w, screenH)),
            Offset(w * 0.08f, h * 0.05f), Size(w * 0.84f, screenH - h * 0.1f), CornerRadius(4.dp.toPx())
        )
        val swirl = Path().apply {
            moveTo(w * 0.30f, h * 0.50f)
            cubicTo(w * 0.35f, h * 0.10f, w * 0.75f, h * 0.15f, w * 0.68f, h * 0.45f)
            cubicTo(w * 0.62f, h * 0.30f, w * 0.45f, h * 0.30f, w * 0.30f, h * 0.50f)
        }
        drawPath(swirl, Color.White.copy(alpha = 0.22f))
        drawRect(Color(0xFF16233F), Offset(w * 0.46f, screenH), Size(w * 0.08f, h * 0.12f))
        drawRoundRect(Color(0xFF16233F), Offset(w * 0.30f, h * 0.86f), Size(w * 0.40f, h * 0.05f), CornerRadius(3.dp.toPx()))
    }
}

/**
 * Compact connection header: monitor illustration, PC name, connection state and two chips.
 * Only values the app really has are shown: PC uptime from the status call and the address used to connect.
 */
@Composable
internal fun DashConnectionHeader(hostname: String, reachable: Boolean, uptime: String?, address: String) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        DashMonitorIllustration(Modifier.width(76.dp))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(hostname, style = MaterialTheme.typography.headlineSmall.copy(fontSize = 22.sp, fontWeight = FontWeight.Bold), maxLines = 1, overflow = TextOverflow.Ellipsis)
            DashStatusPillPlain(if (reachable) "Connected" else "Offline", if (reachable) DashColors.Green else DashColors.Red, reachable)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (uptime != null) DashChip(Glyph.CLOCK, uptime)
                if (address.isNotBlank()) DashChip(Glyph.PIN, address, Modifier.weight(1f, fill = false))
            }
        }
    }
}

/** Dot and word without a pill background, as in the header of the reference. */
@Composable
private fun DashStatusPillPlain(text: String, color: Color, pulsing: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        DashPulseDot(color, pulsing)
        Spacer(Modifier.width(4.dp))
        Text(text, style = MaterialTheme.typography.titleSmall, color = color, maxLines = 1)
    }
}

// ---------------------------------------------------------------------------------------------
// Live screen: quality presets
// ---------------------------------------------------------------------------------------------

/** Decorative preview tile for a preset (an illustration, never a capture of the PC). */
@Composable
private fun DashPresetThumb(q: Quality, modifier: Modifier = Modifier) {
    val (skyTop, skyBottom) = when (q) {
        Quality.LOW, Quality.MEDIUM -> Color(0xFF2B6FD6) to Color(0xFFCFE6FF)
        Quality.HIGH, Quality.NATIVE -> Color(0xFF3A63D8) to Color(0xFFBFE0FF)
        Quality.ULTRA -> Color(0xFF8B5CF6) to Color(0xFFFFB3D9)
        Quality.ULTRA120 -> Color(0xFFE5622B) to Color(0xFFFFD08A)
    }
    Canvas(modifier) {
        val w = size.width; val h = size.height
        drawRect(Brush.verticalGradient(listOf(skyTop, skyBottom)))
        val far = Path().apply { moveTo(0f, h * 0.75f); lineTo(w * 0.30f, h * 0.30f); lineTo(w * 0.55f, h * 0.62f); lineTo(w * 0.75f, h * 0.38f); lineTo(w, h * 0.75f); close() }
        drawPath(far, Color(0xFF28365E))
        val near = Path().apply { moveTo(0f, h); lineTo(w * 0.22f, h * 0.60f); lineTo(w * 0.50f, h * 0.88f); lineTo(w * 0.80f, h * 0.55f); lineTo(w, h); close() }
        drawPath(near, Color(0xFF16213F))
    }
}

@Composable
private fun DashPresetCard(q: Quality, on: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(14.dp)
    val sel by animateFloatAsState(if (on) 1f else 0f, tween(160), label = "presetBorder")
    Column(
        modifier
            .clip(shape)
            .background(if (on) DashColors.Blue.copy(alpha = 0.14f) else Color.White.copy(alpha = 0.04f))
            .border(if (on) 2.dp else 1.dp, if (on) DashColors.Cyan.copy(alpha = 0.6f + 0.4f * sel) else DashColors.PanelBorder, shape)
            .selectable(selected = on, role = Role.RadioButton, onClick = onClick)
            .padding(4.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(Modifier.fillMaxWidth().aspectRatio(1.8f).clip(RoundedCornerShape(10.dp))) {
            DashPresetThumb(q, Modifier.fillMaxSize())
            if (on) Box(
                Modifier.align(Alignment.TopEnd).padding(3.dp).size(18.dp).clip(CircleShape).background(DashColors.Blue),
                contentAlignment = Alignment.Center
            ) { DashIcon(Glyph.CHECK, Color.White, iconSize = 12.dp) }
        }
        Spacer(Modifier.height(3.dp))
        Text(q.label, style = MaterialTheme.typography.labelLarge.copy(fontSize = 12.sp), maxLines = 1, textAlign = TextAlign.Center, overflow = TextOverflow.Ellipsis)
        Text(
            "${q.fps} fps", style = MaterialTheme.typography.labelSmall.copy(fontSize = 11.sp),
            color = DashColors.Muted, maxLines = 1, textAlign = TextAlign.Center
        )
        Spacer(Modifier.height(1.dp))
    }
}

/**
 * All six presets as selectable cards: one row of six when the card is wide and the system font is normal,
 * otherwise two rows of three, so no label is squeezed or clipped. Selection goes straight to [onSelect].
 */
@Composable
internal fun DashPresetSelector(selected: Quality, onSelect: (Quality) -> Unit, modifier: Modifier = Modifier) {
    val fontScale = LocalDensity.current.fontScale
    BoxWithConstraints(modifier.fillMaxWidth()) {
        val columns = if (maxWidth >= 330.dp && fontScale <= 1.15f) 6 else 3
        val gap = if (columns == 6) 5.dp else 8.dp
        Column(Modifier.selectableGroup(), verticalArrangement = Arrangement.spacedBy(gap)) {
            Quality.values().toList().chunked(columns).forEach { rowItems ->
                Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(gap)) {
                    rowItems.forEach { q -> DashPresetCard(q, q == selected, { onSelect(q) }, Modifier.weight(1f).fillMaxHeight()) }
                    repeat(columns - rowItems.size) { Spacer(Modifier.weight(1f)) }
                }
            }
        }
    }
}

/** Prominent blue primary button. */
@Composable
internal fun DashPrimaryButton(text: String, glyph: Glyph, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(16.dp)
    Row(
        modifier.heightIn(min = 46.dp).clip(shape)
            .background(Brush.horizontalGradient(listOf(Color(0xFF1E6BFF), Color(0xFF2FA4FF))))
            .clickable(role = Role.Button, onClick = onClick).padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically
    ) {
        DashIcon(glyph, Color.White, iconSize = 22.dp)
        Spacer(Modifier.width(10.dp))
        Text(text, style = MaterialTheme.typography.titleMedium, color = Color.White, maxLines = 1)
    }
}

// ---------------------------------------------------------------------------------------------
// System performance: CPU / memory / disk / network
// ---------------------------------------------------------------------------------------------

/** Last few real samples of each metric, used for the small trend lines. Filled from the live status. */
internal class MetricHistory {
    val cpu = androidx.compose.runtime.mutableStateListOf<Float>()
    val mem = androidx.compose.runtime.mutableStateListOf<Float>()
    val disk = androidx.compose.runtime.mutableStateListOf<Float>()
    val net = androidx.compose.runtime.mutableStateListOf<Float>()
    fun add(s: PcStatus) {
        push(cpu, s.cpu.toFloat()); push(mem, s.memory.toFloat()); push(disk, s.disk.toFloat())
        push(net, (s.rxPerSec + s.txPerSec).toFloat())
    }
    private fun push(list: androidx.compose.runtime.snapshots.SnapshotStateList<Float>, v: Float) {
        list.add(v); while (list.size > 30) list.removeAt(0)
    }
}

@Composable
private fun DashSparkline(values: List<Float>, color: Color, modifier: Modifier = Modifier, fixedMax: Float? = null) {
    Canvas(modifier) {
        if (values.size < 2) return@Canvas
        val max = fixedMax ?: (values.maxOrNull() ?: 1f).coerceAtLeast(1f)
        val stepX = size.width / (values.size - 1)
        val line = Path(); val fill = Path()
        values.forEachIndexed { i, v ->
            val x = i * stepX
            val y = size.height - (v / max).coerceIn(0f, 1f) * (size.height - 3.dp.toPx()) - 1.5.dp.toPx()
            if (i == 0) { line.moveTo(x, y); fill.moveTo(x, size.height); fill.lineTo(x, y) } else { line.lineTo(x, y); fill.lineTo(x, y) }
        }
        fill.lineTo(size.width, size.height); fill.close()
        drawPath(fill, Brush.verticalGradient(listOf(color.copy(alpha = 0.28f), Color.Transparent)))
        drawPath(line, color, style = Stroke(width = 1.6.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}

@Composable
private fun DashRing(percent: Int?, color: Color, ringSize: Dp) {
    val fraction by animateFloatAsState(
        targetValue = (percent ?: 0).coerceIn(0, 100) / 100f, animationSpec = tween(durationMillis = 700), label = "gauge"
    )
    Box(Modifier.size(ringSize), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = 6.dp.toPx()
            val topLeft = Offset(stroke / 2, stroke / 2)
            val arc = Size(size.width - stroke, size.height - stroke)
            drawArc(Color.White.copy(alpha = 0.08f), 0f, 360f, false, topLeft = topLeft, size = arc, style = Stroke(width = stroke))
            if (fraction > 0f) drawArc(color, -90f, 360f * fraction, false, topLeft = topLeft, size = arc, style = Stroke(width = stroke, cap = StrokeCap.Round))
        }
        Row(verticalAlignment = Alignment.Bottom) {
            Text(if (percent == null) "–" else "$percent", style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold, fontFeatureSettings = "tnum"), maxLines = 1)
            if (percent != null) Text("%", style = MaterialTheme.typography.labelSmall, color = DashColors.Muted, modifier = Modifier.padding(bottom = 3.dp))
        }
    }
}

@Composable
private fun DashMetricPanel(
    glyph: Glyph, label: String, percent: Int?, detail: String, accent: Color, history: List<Float>,
    modifier: Modifier = Modifier, warn: Boolean = false
) {
    val shape = RoundedCornerShape(16.dp)
    // High load turns amber, critical turns red. A word is added next to the name too, so colour is never the only signal.
    val color = when {
        warn && percent != null && percent >= 90 -> DashColors.Red
        warn && percent != null && percent >= 75 -> DashColors.Amber
        else -> accent
    }
    val level = when {
        warn && percent != null && percent >= 90 -> "Critical"
        warn && percent != null && percent >= 75 -> "High"
        else -> null
    }
    Column(
        modifier.clip(shape).background(DashColors.Inner).border(1.dp, DashColors.PanelBorder, shape).padding(top = 6.dp, start = 4.dp, end = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.Start) { DashIcon(glyph, color, iconSize = 16.dp) }
        DashRing(percent, color, 46.dp)
        Spacer(Modifier.height(2.dp))
        Text(label + (level?.let { " · $it" } ?: ""), style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(detail, style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp), color = DashColors.Muted, textAlign = TextAlign.Center, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.height(4.dp))
        DashSparkline(history, color, Modifier.fillMaxWidth().height(14.dp), fixedMax = 100f)
    }
}

@Composable
private fun DashRateRow(bytesPerSec: Long?, glyph: Glyph, tint: Color) {
    val text = bytesPerSec?.let { formatBytes(it) }
    val number = text?.substringBefore(' ') ?: "–"
    val unit = if (text == null) "" else text.substringAfter(' ') + "/s"
    // Number above unit: the pair needs far less width than "5.1 MB/s" on one line, so it is never cut off.
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(22.dp).clip(CircleShape).background(tint), contentAlignment = Alignment.Center) { DashIcon(glyph, Color.White, iconSize = 14.dp) }
        Spacer(Modifier.width(5.dp))
        Column {
            Text(number, style = MaterialTheme.typography.labelLarge.copy(fontFeatureSettings = "tnum"), maxLines = 1)
            Text(unit, style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp), color = DashColors.Muted, maxLines = 1, softWrap = false)
        }
    }
}

@Composable
private fun DashNetworkPanel(rx: Long?, tx: Long?, history: List<Float>, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(16.dp)
    Column(modifier.clip(shape).background(DashColors.Inner).border(1.dp, DashColors.PanelBorder, shape).padding(top = 6.dp, start = 4.dp, end = 4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            DashIcon(Glyph.WIFI, DashColors.Cyan, iconSize = 16.dp)
            Spacer(Modifier.width(4.dp))
            Text("Network", style = MaterialTheme.typography.labelLarge.copy(fontSize = 12.sp), maxLines = 1, softWrap = false)
        }
        Spacer(Modifier.height(6.dp))
        DashRateRow(rx, Glyph.DOWN, DashColors.Blue)
        Spacer(Modifier.height(6.dp))
        DashRateRow(tx, Glyph.UP, DashColors.Violet)
        Spacer(Modifier.weight(1f, fill = true))
        Spacer(Modifier.height(4.dp))
        DashSparkline(history, DashColors.Amber, Modifier.fillMaxWidth().height(14.dp))
    }
}

/** One card with CPU, memory, disk and network. Four panels in a row, or a 2 x 2 grid on narrow screens / large fonts. */
@Composable
internal fun DashSystemPanel(
    status: PcStatus?, reachable: Boolean, history: MetricHistory, modifier: Modifier = Modifier
) {
    val fontScale = LocalDensity.current.fontScale
    DashPanel(modifier) {
        DashSectionHeader(Glyph.BARS, "System Performance") {
            if (reachable) DashStatusPill("Live", DashColors.Green, pulsing = true) else DashStatusPill("Offline", DashColors.Red, pulsing = false)
        }
        Spacer(Modifier.height(8.dp))
        // Values are stale while the PC is unreachable, so dim them.
        BoxWithConstraints(Modifier.fillMaxWidth().alpha(if (reachable) 1f else 0.55f)) {
            val perRow = if (maxWidth >= 340.dp && fontScale <= 1.15f) 4 else 2
            val gap = 8.dp
            val panels: List<@Composable (Modifier) -> Unit> = listOf(
                { m -> DashMetricPanel(Glyph.CPU, "CPU", status?.cpu, "Processor load", DashColors.Blue, history.cpu, m, warn = true) },
                { m -> DashMetricPanel(Glyph.MEMORY, "Memory", status?.memory, status?.let { "${gbShort(it.memUsed)} / ${gbShort(it.memTotal)} GB" } ?: "–", DashColors.Violet, history.mem, m, warn = true) },
                { m -> DashMetricPanel(Glyph.DISK, "Disk", status?.disk, status?.let { "${gbShort(it.diskUsed, 0)} / ${gbShort(it.diskTotal, 0)} GB" } ?: "–", DashColors.Green, history.disk, m, warn = true) },
                { m -> DashNetworkPanel(status?.rxPerSec, status?.txPerSec, history.net, m) }
            )
            Column(verticalArrangement = Arrangement.spacedBy(gap)) {
                panels.chunked(perRow).forEach { group ->
                    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(gap)) {
                        group.forEach { p -> p(Modifier.weight(1f).fillMaxHeight()) }
                    }
                }
            }
        }
    }
}

private fun gbShort(bytes: Long, decimals: Int = 1): String =
    String.format(java.util.Locale.US, "%.${decimals}f", bytes / (1024.0 * 1024.0 * 1024.0))

// ---------------------------------------------------------------------------------------------
// Power
// ---------------------------------------------------------------------------------------------

/** Touch tile for one power action: coloured icon, name and a short subtitle. */
@Composable
internal fun DashPowerTile(
    label: String, subtitle: String, glyph: Glyph, tint: Color,
    onClick: () -> Unit, modifier: Modifier = Modifier
) {
    val shape = RoundedCornerShape(16.dp)
    val interaction = remember { MutableInteractionSource() }
    val pressed by interaction.collectIsPressedAsState()
    val scale by animateFloatAsState(targetValue = if (pressed) 0.96f else 1f, animationSpec = tween(durationMillis = 120), label = "press")
    Column(
        modifier
            .scale(scale)
            .heightIn(min = 68.dp)
            .clip(shape)
            .background(Brush.verticalGradient(listOf(tint.copy(alpha = 0.30f), tint.copy(alpha = 0.10f))))
            .border(1.dp, tint.copy(alpha = 0.55f), shape)
            .clickable(interactionSource = interaction, indication = LocalIndication.current, role = Role.Button, onClick = onClick)
            .padding(horizontal = 2.dp, vertical = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        DashIcon(glyph, tint, iconSize = 24.dp)
        Spacer(Modifier.height(4.dp))
        Text(label, style = MaterialTheme.typography.labelLarge.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, textAlign = TextAlign.Center)
        Text(subtitle, style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp), color = DashColors.Muted, maxLines = 2, textAlign = TextAlign.Center)
    }
}

// ---------------------------------------------------------------------------------------------
// Buttons used by the PIN card
// ---------------------------------------------------------------------------------------------

@Composable
internal fun DashOutlineButton(
    text: String, glyph: Glyph, tint: Color, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true
) {
    val shape = RoundedCornerShape(14.dp)
    val c = if (enabled) tint else DashColors.Muted.copy(alpha = 0.5f)
    Row(
        modifier.heightIn(min = 44.dp).clip(shape).background(c.copy(alpha = 0.08f)).border(1.5.dp, c.copy(alpha = 0.7f), shape)
            .then(if (enabled) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier)
            .padding(horizontal = 10.dp),
        horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically
    ) {
        DashIcon(glyph, c, iconSize = 18.dp)
        Spacer(Modifier.width(6.dp))
        Text(text, style = MaterialTheme.typography.labelLarge, color = if (enabled) Color.White else c, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

// ---------------------------------------------------------------------------------------------
// Bottom navigation
// ---------------------------------------------------------------------------------------------

internal enum class NavTab(val label: String, val glyph: Glyph) {
    HOME("Home", Glyph.HOME), LIVE("PC Live", Glyph.MONITOR), SETTINGS("Settings", Glyph.GEAR)
}

/** Exactly three destinations. Home and Settings switch the page; PC Live starts the existing screen session. */
@Composable
internal fun DashBottomNav(selected: NavTab, onSelect: (NavTab) -> Unit) {
    val barShape = RoundedCornerShape(topStart = 22.dp, topEnd = 22.dp)
    // Fully opaque (solid base, then the gradient) and clipped to its own shape, so nothing shows through or past it.
    // The navigation-bar inset is added inside the bar's own background, so the bar grows to cover that area.
    Box(
        Modifier.fillMaxWidth()
            .clip(barShape)
            .background(DashColors.BgBottom)
            .background(Brush.verticalGradient(listOf(DashColors.PanelTop, DashColors.BgBottom)))
            .border(1.dp, DashColors.PanelBorder, barShape)
            .navigationBarsPadding()
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 3.dp).selectableGroup(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            NavTab.values().forEach { tab ->
                val on = tab == selected
                val tint = if (on) DashColors.Blue else DashColors.Muted
                val shape = RoundedCornerShape(16.dp)
                Column(
                    Modifier.weight(1f).heightIn(min = 48.dp).clip(shape)
                        .background(if (on) DashColors.Blue.copy(alpha = 0.14f) else Color.Transparent)
                        .selectable(selected = on, role = Role.Tab, onClick = { onSelect(tab) })
                        .padding(vertical = 4.dp),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center
                ) {
                    DashIcon(tab.glyph, tint, iconSize = 22.dp)
                    Spacer(Modifier.height(1.dp))
                    Text(tab.label, style = MaterialTheme.typography.labelMedium, color = tint, maxLines = 1)
                    Box(Modifier.padding(top = 2.dp).width(if (on) 32.dp else 0.dp).height(3.dp).clip(CircleShape).background(DashColors.Blue))
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
    val color = if (isError) DashColors.Red else DashColors.Blue
    val shape = RoundedCornerShape(14.dp)
    Text(
        text,
        Modifier.fillMaxWidth().clip(shape).background(color.copy(alpha = 0.12f)).border(1.dp, color.copy(alpha = 0.30f), shape).padding(12.dp),
        style = MaterialTheme.typography.bodySmall, color = color, textAlign = TextAlign.Center
    )
}
