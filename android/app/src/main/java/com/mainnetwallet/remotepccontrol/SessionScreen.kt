package com.mainnetwallet.remotepccontrol

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.pm.ActivityInfo
import android.graphics.Bitmap
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.delay
import org.json.JSONObject
import org.webrtc.RendererCommon
import org.webrtc.SurfaceViewRenderer
import org.webrtc.VideoTrack
import java.util.concurrent.atomic.AtomicInteger
import kotlin.math.cos
import kotlin.math.sin

enum class TouchMode(val label: String, val hint: String) {
    OFF("Off", "Screen is view-only; use the trackpad"),
    CLICK("Click", "Drag anywhere = move the pointer from where it is · tap = click there · long-press = right click"),
    DRAG("Drag", "Drag = hold the left button (select, move windows)"),
    SCROLL("Scroll", "Drag up/down to scroll the page")
}

fun TouchMode.next(): TouchMode = TouchMode.values().let { it[(ordinal + 1) % it.size] }


val QUICK_KEYS = listOf(
    "Esc" to """{"type":"key","key":"ESC"}""",
    "Tab" to """{"type":"key","key":"TAB"}""",
    "⌫" to """{"type":"key","key":"BACKSPACE"}""",
    "Enter" to """{"type":"key","key":"ENTER"}""",
    "←" to """{"type":"key","key":"LEFT"}""",
    "↑" to """{"type":"key","key":"UP"}""",
    "↓" to """{"type":"key","key":"DOWN"}""",
    "→" to """{"type":"key","key":"RIGHT"}""",
    "Win" to """{"type":"key","key":"WIN"}""",
    "Alt+Tab" to """{"type":"hotkey","keys":["ALT","TAB"]}""",
    "Ctrl+C" to """{"type":"hotkey","keys":["CTRL","C"]}""",
    "Ctrl+V" to """{"type":"hotkey","keys":["CTRL","V"]}""",
    "Ctrl+A" to """{"type":"hotkey","keys":["CTRL","A"]}""",
    "Ctrl+Z" to """{"type":"hotkey","keys":["CTRL","Z"]}"""
)


@Composable
fun PadButtons(
    send: (JSONObject) -> Unit, modifier: Modifier = Modifier,
    showKeys: Boolean? = null, onShowKeys: ((Boolean) -> Unit)? = null
) {
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Button(onClick = { send(JSONObject().put("type", "click").put("button", "left")) }, modifier = Modifier.weight(1f).height(48.dp)) { Text("Left click") }
        Button(onClick = { send(JSONObject().put("type", "click").put("button", "right")) }, modifier = Modifier.weight(1f).height(48.dp)) { Text("Right click") }
        if (showKeys != null && onShowKeys != null) {
            if (showKeys) Button(onClick = { onShowKeys(false) }, modifier = Modifier.height(48.dp)) { Text("Keys") }
            else OutlinedButton(onClick = { onShowKeys(true) }, modifier = Modifier.height(48.dp)) { Text("Keys") }
        }
    }
}

@Composable
fun SpeedRow(sensitivity: Float, onSensitivity: (Float) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text("Speed", style = MaterialTheme.typography.bodySmall)
        Slider(value = sensitivity, onValueChange = onSensitivity, valueRange = 0.5f..4f, modifier = Modifier.weight(1f).padding(horizontal = 8.dp))
        Text(String.format(java.util.Locale.US, "%.1fx", sensitivity), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
fun KeysPanel(send: (JSONObject) -> Unit, typeText: String, onTypeText: (String) -> Unit, onSendText: () -> Unit) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        QuickKeyBar(send)
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedTextField(value = typeText, onValueChange = onTypeText, label = { Text("Text to type on PC") }, modifier = Modifier.weight(1f), singleLine = true)
            Button(onClick = onSendText) { Text("Send") }
        }
    }
}


/** Click mode: how far the pointer moves per finger movement (1x was the old speed; now 2x, one step faster). */
private const val CLICK_DRAG_GAIN = 2f

/**
 * Shows the PC frame and turns touches into mouse input.
 * Coordinates are sent normalized (0..1 of the visible picture), so they stay correct whatever
 * size the frame is scaled to. The box is sized to the frame's aspect ratio (no letterbox),
 * so a touch maps 1:1 onto the picture.
 */
@Composable
fun ScreenView(
    aspect: Float, mode: TouchMode, send: (JSONObject) -> Unit, onPosition: (Double, Double) -> Unit, modifier: Modifier = Modifier,
    cursor: () -> Offset? = { null },   // pointer as 0..1 of the picture; read while drawing, so moving it never recomposes
    content: @Composable () -> Unit     // the picture itself: a Bitmap (WebSocket stream) or the WebRTC video
) {
    fun emit(type: String, p: Offset, size: androidx.compose.ui.unit.IntSize, button: String? = null) {
        if (size.width == 0 || size.height == 0) return
        val nx = (p.x / size.width).coerceIn(0f, 1f).toDouble()
        val ny = (p.y / size.height).coerceIn(0f, 1f).toDouble()
        onPosition(nx, ny)
        val o = JSONObject().put("type", type).put("nx", nx).put("ny", ny)
        if (button != null) o.put("button", button)
        send(o)
    }
    Box(modifier, contentAlignment = Alignment.Center) {
        Box(
            // Keys are the mode only (never the frame): restarting on every frame would cancel taps in flight.
            modifier = Modifier.aspectRatio(aspect)
                .background(Color.Black, RoundedCornerShape(6.dp))
                .pointerInput(mode) {
                    if (mode != TouchMode.CLICK) return@pointerInput
                    detectTapGestures(
                        // Click where the pointer already is (no position sent): the finger only moves the pointer, it never jumps it.
                        onTap = { send(JSONObject().put("type", "click").put("button", "left")) },
                        onLongPress = { send(JSONObject().put("type", "click").put("button", "right")) }
                    )
                }
                .pointerInput(mode) {
                    if (mode == TouchMode.OFF) return@pointerInput   // Click mode also moves the pointer on drag (a plain tap still clicks)
                    var last = Offset.Zero
                    var lastSentNs = 0L
                    var scrollAcc = 0f
                    var cur = Offset(0.5f, 0.5f)   // Click mode: the pointer as 0..1 of the picture; the finger only nudges it from here
                    var accX = 0f
                    var accY = 0f
                    val stepPx = 24.dp.toPx()
                    detectDragGestures(
                        onDragStart = { p ->
                            last = p; scrollAcc = 0f; accX = 0f; accY = 0f
                            if (mode == TouchMode.DRAG) emit("down", p, size, "left") else if (mode == TouchMode.CLICK) cur = cursor() ?: cur
                        },
                        onDragEnd = { if (mode == TouchMode.DRAG) emit("up", last, size, "left") },
                        onDragCancel = { if (mode == TouchMode.DRAG) emit("up", last, size, "left") },
                        onDrag = { change, amount ->
                            change.consume()
                            last = change.position
                            if (mode == TouchMode.SCROLL) {
                                // Finger moves down -> page scrolls up, like a phone (content follows the finger).
                                scrollAcc += amount.y
                                val steps = (scrollAcc / stepPx).toInt()
                                if (steps != 0) { send(JSONObject().put("type", "scroll").put("dy", steps)); scrollAcc -= steps * stepPx }
                            } else if (mode == TouchMode.CLICK) {
                                // Trackpad style: the pointer keeps its place and moves by how far the finger moves, wherever the finger is.
                                accX += amount.x * CLICK_DRAG_GAIN; accY += amount.y * CLICK_DRAG_GAIN
                                val now = System.nanoTime()
                                if (size.width > 0 && size.height > 0 && now - lastSentNs >= 16_000_000L) {
                                    lastSentNs = now
                                    cur = Offset((cur.x + accX / size.width).coerceIn(0f, 1f), (cur.y + accY / size.height).coerceIn(0f, 1f))
                                    accX = 0f; accY = 0f
                                    emit("move", Offset(cur.x * size.width, cur.y * size.height), size)
                                }
                            } else {
                                val now = System.nanoTime()
                                if (now - lastSentNs >= 16_000_000L) { lastSentNs = now; emit("move", change.position, size) }
                            }
                        }
                    )
                }
                .drawWithContent { drawContent(); drawPointer(cursor()) }
        ) { content() }
    }
}

/** The WebRTC video of the PC screen, drawn by a hardware-scaled SurfaceViewRenderer. */
@Composable
private fun RtcVideo(track: VideoTrack?, onSize: (Int, Int) -> Unit) {
    var renderer by remember { mutableStateOf<SurfaceViewRenderer?>(null) }
    DisposableEffect(track, renderer) {
        val r = renderer
        if (track != null && r != null) track.addSink(r)
        onDispose { if (track != null && r != null) track.removeSink(r) }
    }
    AndroidView(
        factory = { ctx ->
            SurfaceViewRenderer(ctx).apply {
                init(RtcEngine.egl.eglBaseContext, object : RendererCommon.RendererEvents {
                    override fun onFirstFrameRendered() {}
                    override fun onFrameResolutionChanged(videoWidth: Int, videoHeight: Int, rotation: Int) {
                        // The picture's real shape: keeps touch positions exact even before the PC's size message arrives.
                        if (rotation % 180 == 0) onSize(videoWidth, videoHeight) else onSize(videoHeight, videoWidth)
                    }
                })
                setEnableHardwareScaler(true)
                setScalingType(RendererCommon.ScalingType.SCALE_ASPECT_FIT)
                renderer = this
            }
        },
        modifier = Modifier.fillMaxSize(),
        onRelease = { it.release(); renderer = null }
    )
}


/** The mouse pointer (same arrow the PC agent used to bake into the frames), drawn on top of the picture. */
private fun DrawScope.drawPointer(p: Offset?) {
    if (p == null) return
    val s = maxOf(size.width / 80f, 9.dp.toPx())
    val x = p.x * size.width
    val y = p.y * size.height
    val arrow = Path().apply {
        moveTo(x, y); lineTo(x, y + s * 1.6f); lineTo(x + s * 0.45f, y + s * 1.25f); lineTo(x + s * 0.8f, y + s * 1.9f)
        lineTo(x + s * 1.1f, y + s * 1.75f); lineTo(x + s * 0.75f, y + s * 1.15f); lineTo(x + s * 1.25f, y + s * 1.1f)
        close()
    }
    drawPath(arrow, Color.White)
    drawPath(arrow, Color.Black, style = Stroke(width = 1.2f.dp.toPx()))
}

/** Circular arrow ("rotate screen") drawn with a Canvas, so no icon library is needed. */
@Composable
private fun RotateIcon(color: Color, modifier: Modifier = Modifier) {
    Canvas(modifier.size(18.dp)) {
        val s = size.minDimension
        val center = Offset(s / 2f, s / 2f)
        val r = s * 0.36f
        val start = -60f
        val sweep = 270f
        drawArc(
            color, start, sweep, false,
            topLeft = Offset(center.x - r, center.y - r), size = Size(2 * r, 2 * r),
            style = Stroke(width = s * 0.1f, cap = StrokeCap.Round)
        )
        // Arrow head at the end of the arc, pointing in the direction of travel (clockwise).
        val a = Math.toRadians((start + sweep).toDouble())
        val rx = cos(a).toFloat(); val ry = sin(a).toFloat()      // radial direction
        val tx = -ry; val ty = rx                                 // tangent (clockwise)
        val ex = center.x + r * rx; val ey = center.y + r * ry
        val head = s * 0.24f
        val arrow = Path().apply {
            moveTo(ex + tx * head, ey + ty * head)
            lineTo(ex + rx * head * 0.8f, ey + ry * head * 0.8f)
            lineTo(ex - rx * head * 0.8f, ey - ry * head * 0.8f)
            close()
        }
        drawPath(arrow, color)
    }
}

/** Toggles the phone between portrait and landscape, even when auto-rotate is off in Android. */
@Composable
private fun RotateButton(onClick: () -> Unit, tonal: Boolean, small: Boolean = false, modifier: Modifier = Modifier, height: androidx.compose.ui.unit.Dp = 32.dp) {
    val content: @Composable androidx.compose.foundation.layout.RowScope.() -> Unit = {
        RotateIcon(LocalContentColor.current, Modifier.semantics { contentDescription = "Rotate screen" })
        Spacer(Modifier.width(4.dp))
        Text("Rotate", style = if (small) MaterialTheme.typography.labelSmall else LocalTextStyle.current)
    }
    val size = if (small) modifier.height(height) else modifier
    val pad = if (small) menuPadding else compactPadding
    if (tonal) FilledTonalButton(onClick = onClick, modifier = size, contentPadding = pad, content = content)
    else OutlinedButton(onClick = onClick, modifier = size, contentPadding = pad, content = content)
}

private fun Context.findActivity(): Activity? {
    var c: Context? = this
    while (c is ContextWrapper) { if (c is Activity) return c; c = c.baseContext }
    return null
}

/** Portrait toolbar: one row (Quality, Fullscreen, Rotate, Stop) that always fits the screen width. */
@Composable
private fun SessionToolbar(
    quality: Quality, onQuality: (Quality) -> Unit, onRotate: () -> Unit, onFullscreen: () -> Unit, onStop: () -> Unit
) {
    val pad = PaddingValues(horizontal = 4.dp, vertical = 0.dp)
    val label = MaterialTheme.typography.labelMedium
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        QualityMenuButton(quality, onQuality, Modifier.weight(2.2f), compact = true)
        OutlinedButton(onClick = onFullscreen, modifier = Modifier.weight(1.6f).height(36.dp), contentPadding = pad) { Text("Fullscreen", style = label, maxLines = 1) }
        RotateButton(onRotate, tonal = false, small = true, modifier = Modifier.weight(1.3f), height = 36.dp)
        StopButton(onStop, Modifier.weight(0.9f).height(36.dp), pad)
    }
}

@Composable
private fun StopButton(onStop: () -> Unit, modifier: Modifier = Modifier, pad: PaddingValues = compactPadding) {
    Button(
        onClick = onStop, modifier = modifier, contentPadding = pad,
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.errorContainer, contentColor = MaterialTheme.colorScheme.onErrorContainer)
    ) { Text("Stop", style = if (pad === compactPadding) LocalTextStyle.current else MaterialTheme.typography.labelMedium, maxLines = 1) }
}

/** Full-width 32 dp button for the slim column beside the PC picture; the active touch mode is highlighted. */
@Composable
private fun SideButton(text: String, selected: Boolean, onClick: () -> Unit) {
    val m = Modifier.fillMaxWidth().height(32.dp)
    val pad = PaddingValues(horizontal = 2.dp, vertical = 0.dp)
    if (selected) Button(onClick = onClick, modifier = m, contentPadding = pad) { Text(text, style = MaterialTheme.typography.labelSmall, maxLines = 1) }
    else FilledTonalButton(onClick = onClick, modifier = m, contentPadding = pad) { Text(text, style = MaterialTheme.typography.labelSmall, maxLines = 1) }
}

/** Small tonal button (32 dp high) used inside the landscape Controls menu. */
@Composable
private fun MenuButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    FilledTonalButton(onClick = onClick, modifier = modifier.height(32.dp), contentPadding = menuPadding) {
        Text(text, style = MaterialTheme.typography.labelSmall, maxLines = 1)
    }
}

@Composable
private fun QuickKeyBar(send: (JSONObject) -> Unit) {
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        QUICK_KEYS.forEach { (label, json) ->
            OutlinedButton(onClick = { send(JSONObject(json)) }, contentPadding = compactPadding) { Text(label) }
        }
    }
}

/** Small corner label: transport, resolution, frames per second and (WebRTC) round-trip time. */
@Composable
private fun StreamStatsOverlay(c: RemoteController, modifier: Modifier = Modifier) {
    var fps by remember { mutableIntStateOf(0) }
    LaunchedEffect(c.frameCounter) {
        var last = c.frameCounter.get()
        while (true) {
            delay(1000)
            val now = c.frameCounter.get()
            fps = now - last; last = now
        }
    }
    val info = c.streamInfo
    val rtc = c.rtcStats
    val label = when {
        c.transport == "WebRTC" -> {
            val size = if (info != null) "${info.width}\u00D7${info.height} \u00B7 " else ""
            val rtt = if (rtc != null && rtc.rttMs >= 0) " \u00B7 ${rtc.rttMs} ms" else ""
            "WebRTC \u00B7 $size${rtc?.fps ?: 0} fps$rtt"
        }
        c.transport == "Connecting" -> "Connecting\u2026"
        info != null -> {
            val cap = if (info.targetFps > 0) "/${info.targetFps}" else ""
            val why = if (c.rtcFallbackReason.isNotEmpty()) " \u00B7 WebRTC: ${c.rtcFallbackReason}" else ""
            "WebSocket \u00B7 ${info.width}\u00D7${info.height} \u00B7 $fps$cap fps$why"
        }
        else -> return
    }
    Text(
        label,
        color = Color.White, style = MaterialTheme.typography.labelSmall,
        modifier = modifier.background(Color(0x99000000), RoundedCornerShape(8.dp)).padding(horizontal = 8.dp, vertical = 3.dp)
    )
}

/** The PC picture (or a waiting placeholder) with the stats overlay in its top-left corner. */
@Composable
private fun ScreenArea(c: RemoteController, mode: TouchMode, modifier: Modifier, frameModifier: Modifier, waitingModifier: Modifier) {
    val frame = c.frame
    val track = c.videoTrack
    val cursor: () -> Offset? = { if (c.cursorX >= 0f) Offset(c.cursorX, c.cursorY) else null }
    Box(modifier) {
        if (track != null) ScreenView(
            c.videoAspect, mode, { c.sendInput(it) }, { _, _ -> }, frameModifier, cursor = cursor
        ) { RtcVideo(track) { w, h -> c.onVideoSize(w, h) } }
        else if (frame != null) ScreenView(
            frame.width.toFloat() / frame.height.toFloat(), mode, { c.sendInput(it) }, { _, _ -> }, frameModifier, cursor = cursor
        ) {
            Image(
                bitmap = remember(frame) { frame.asImageBitmap() },
                filterQuality = FilterQuality.High,   // bicubic scaling: sharp text when the frame is shown larger or smaller than sent
                contentDescription = "Live Windows desktop. Touch to control the mouse.",
                contentScale = ContentScale.FillBounds,
                modifier = Modifier.fillMaxSize()
            )
        }
        else Box(waitingModifier, contentAlignment = Alignment.Center) { Text("Waiting for the PC screen\u2026", color = Color.White) }
        StreamStatsOverlay(c, Modifier.align(Alignment.TopStart).padding(6.dp))
    }
}

/**
 * Full-window session UI.
 * Portrait: PC screen on top (exact aspect ratio), trackpad below.
 * Landscape: PC screen on the left, trackpad panel on the right (hideable; the screen then fills the window).
 */
@Composable
fun SessionScreen(c: RemoteController) {
    var touchMode by remember { mutableStateOf(TouchMode.OFF) }
    var sensitivity by rememberSaveable { mutableStateOf(2.5f) }
    var showPad by rememberSaveable { mutableStateOf(true) }
    var showKeys by rememberSaveable { mutableStateOf(false) }
    var showControls by rememberSaveable { mutableStateOf(false) }   // landscape: Touch/Keys/Fullscreen/Rotate shown in the panel under the Controls button (hidden until tapped)
    var typeText by rememberSaveable { mutableStateOf("") }
    val send: (JSONObject) -> Unit = { c.sendInput(it) }
    val onSendText: () -> Unit = {
        if (typeText.isNotEmpty()) { send(JSONObject().put("type", "type").put("text", typeText.take(500))); typeText = "" }
    }
    val activity = LocalContext.current.findActivity()
    // Back to the normal (sensor / auto-rotate) behaviour when the session ends.
    DisposableEffect(Unit) { onDispose { activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED } }

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val windowWidth = maxWidth
        val windowHeight = maxHeight   // read here: BoxWithConstraints' scope is not reachable from inside Column
        val isLandscape = maxWidth > maxHeight
        val rotate: () -> Unit = {
            activity?.requestedOrientation =
                if (isLandscape) ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT else ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        }
        if (maxWidth > maxHeight) {
            // Landscape: PC screen on the left, a separate trackpad panel on the right.
            // The Controls button sits at the top-right of the panel; tapping it shows Touch, Keys, Fullscreen and Rotate inside the panel (never over the PC picture).
            // Quality and Stop are only in the portrait toolbar.
            val panelWidth = (windowWidth * 0.28f).coerceIn(230.dp, 340.dp)
            Box(Modifier.fillMaxSize().background(Color.Black).safeDrawingPadding()) {
                Row(Modifier.fillMaxSize()) {
                    Box(Modifier.weight(1f).fillMaxHeight()) {
                        ScreenArea(c, touchMode, Modifier.fillMaxSize(), Modifier.fillMaxSize(), Modifier.fillMaxSize())
                        if (showKeys) Surface(
                            Modifier.align(Alignment.BottomStart).fillMaxWidth().padding(8.dp),
                            color = MaterialTheme.colorScheme.surface.copy(alpha = 0.93f), shape = RoundedCornerShape(16.dp)
                        ) { Box(Modifier.padding(8.dp)) { KeysPanel(send, typeText, { typeText = it }, onSendText) } }
                    }
                    // Panel hidden: a slim column in the free space to the right of the PC picture (nothing is drawn over the screen).
                    // Exit (brings the panel back as it was) on top, then touch modes and left/right click; the active mode is highlighted.
                    if (!showPad) Column(
                        Modifier.width(68.dp).fillMaxHeight().padding(horizontal = 4.dp, vertical = 6.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp, Alignment.CenterVertically)
                    ) {
                        SideButton("Exit", false, { showPad = true })
                        listOf(TouchMode.OFF, TouchMode.CLICK, TouchMode.SCROLL, TouchMode.DRAG).forEach { m ->
                            SideButton(m.label, m == touchMode, { touchMode = m })
                        }
                        SideButton("L-click", false, { send(JSONObject().put("type", "click").put("button", "left")) })
                        SideButton("R-click", false, { send(JSONObject().put("type", "click").put("button", "right")) })
                    }
                    if (showPad) Column(
                        Modifier.width(panelWidth).fillMaxHeight().background(MaterialTheme.colorScheme.surface).padding(8.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        // Controls button top-right of the panel; its buttons wrap inside the panel width, never over the PC picture.
                        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            MenuButton(if (showControls) "Controls \u25B4" else "Controls \u25BE", { showControls = !showControls }, Modifier.fillMaxWidth())
                            if (showControls) {
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                    MenuButton("Touch: ${touchMode.label}", { touchMode = touchMode.next() }, Modifier.weight(1f))
                                    MenuButton("Keys", { showKeys = !showKeys }, Modifier.weight(1f))
                                }
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                    MenuButton("Fullscreen", { showPad = false }, Modifier.weight(1f))
                                    RotateButton(rotate, tonal = true, small = true, modifier = Modifier.weight(1f))
                                }
                            }
                        }
                        Trackpad(sensitivity, send, Modifier.weight(1f).fillMaxWidth())
                        PadButtons(send)
                        SpeedRow(sensitivity) { sensitivity = it }
                    }
                }
            }
        } else {
            Column(
                Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding().padding(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                SessionToolbar(
                    c.quality, { c.setQuality(it) }, rotate,
                    // Fullscreen: landscape with the panel hidden, so the PC picture gets the whole screen (Exit brings the panel back).
                    { showPad = false; activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE },
                    { c.stopScreen() }
                )
                ScreenArea(
                    c, touchMode,
                    Modifier.fillMaxWidth().weight(1f).background(Color.Black, RoundedCornerShape(6.dp)),
                    Modifier.fillMaxSize(),
                    Modifier.fillMaxSize()
                )
                // Trackpad stays compact (about a quarter of the window) so the PC screen gets the rest.
                Trackpad(sensitivity, send, Modifier.fillMaxWidth().height(maxOf(110.dp, minOf(200.dp, windowHeight * 0.26f))))
                PadButtons(send, showKeys = showKeys, onShowKeys = { showKeys = it })
                SpeedRow(sensitivity) { sensitivity = it }
                if (showKeys) KeysPanel(send, typeText, { typeText = it }, onSendText)
            }
        }
    }
}
