package com.mainnetwallet.remotepccontrol

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.FilterQuality
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicInteger

enum class TouchMode(val label: String, val hint: String) {
    OFF("Off", "Screen is view-only; use the trackpad"),
    CLICK("Click", "Tap = click · long-press = right click"),
    MOVE("Move", "Drag to move the pointer without clicking"),
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
        Slider(value = sensitivity, onValueChange = onSensitivity, valueRange = 0.5f..3f, modifier = Modifier.weight(1f).padding(horizontal = 8.dp))
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


/**
 * Shows the PC frame and turns touches into mouse input.
 * Coordinates are sent normalized (0..1 of the visible picture), so they stay correct whatever
 * size the frame is scaled to. The box is sized to the frame's aspect ratio (no letterbox),
 * so a touch maps 1:1 onto the picture.
 */
@Composable
fun ScreenView(
    frame: Bitmap, mode: TouchMode, send: (JSONObject) -> Unit, onPosition: (Double, Double) -> Unit, modifier: Modifier = Modifier,
    cursor: () -> Offset? = { null }   // pointer as 0..1 of the picture; read while drawing, so moving it never recomposes
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
        Image(
            bitmap = remember(frame) { frame.asImageBitmap() },
            filterQuality = FilterQuality.High,   // bicubic scaling: sharp text when the frame is shown larger or smaller than sent
            contentDescription = "Live Windows desktop. Touch to control the mouse.",
            contentScale = ContentScale.FillBounds,
            // Keys are the mode only (never the frame): restarting on every frame would cancel taps in flight.
            modifier = Modifier.aspectRatio(frame.width.toFloat() / frame.height.toFloat())
                .background(Color.Black, RoundedCornerShape(6.dp))
                .pointerInput(mode) {
                    if (mode != TouchMode.CLICK) return@pointerInput
                    detectTapGestures(
                        onTap = { p -> emit("click", p, size, "left") },
                        onLongPress = { p -> emit("click", p, size, "right") }
                    )
                }
                .pointerInput(mode) {
                    if (mode == TouchMode.CLICK || mode == TouchMode.OFF) return@pointerInput
                    var last = Offset.Zero
                    var lastSentNs = 0L
                    var scrollAcc = 0f
                    val stepPx = 24.dp.toPx()
                    detectDragGestures(
                        onDragStart = { p ->
                            last = p; scrollAcc = 0f
                            if (mode == TouchMode.DRAG) emit("down", p, size, "left") else if (mode == TouchMode.MOVE) emit("move", p, size)
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
                            } else {
                                val now = System.nanoTime()
                                if (now - lastSentNs >= 16_000_000L) { lastSentNs = now; emit("move", change.position, size) }
                            }
                        }
                    )
                }
                .drawWithContent { drawContent(); drawPointer(cursor()) }
        )
    }
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

@Composable
private fun SessionToolbar(
    mode: TouchMode, onMode: (TouchMode) -> Unit, onDoubleClick: () -> Unit,
    quality: Quality, onQuality: (Quality) -> Unit, onStop: () -> Unit
) {
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        TouchMode.values().forEach { m ->
            if (m == mode) Button(onClick = { onMode(m) }, contentPadding = compactPadding) { Text(m.label) }
            else OutlinedButton(onClick = { onMode(m) }, contentPadding = compactPadding) { Text(m.label) }
        }
        OutlinedButton(onClick = onDoubleClick, contentPadding = compactPadding) { Text("Double-click") }
        QualityMenuButton(quality, onQuality)
        StopButton(onStop)
    }
}

@Composable
private fun StopButton(onStop: () -> Unit) {
    Button(
        onClick = onStop, contentPadding = compactPadding,
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.errorContainer, contentColor = MaterialTheme.colorScheme.onErrorContainer)
    ) { Text("Stop") }
}

@Composable
private fun QuickKeyBar(send: (JSONObject) -> Unit) {
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        QUICK_KEYS.forEach { (label, json) ->
            OutlinedButton(onClick = { send(JSONObject(json)) }, contentPadding = compactPadding) { Text(label) }
        }
    }
}

/** Small corner label: resolution of the frames being received and measured / maximum frames per second. */
@Composable
private fun StreamStatsOverlay(info: StreamInfo?, frameCounter: AtomicInteger, modifier: Modifier = Modifier) {
    var fps by remember { mutableIntStateOf(0) }
    LaunchedEffect(frameCounter) {
        var last = frameCounter.get()
        while (true) {
            delay(1000)
            val now = frameCounter.get()
            fps = now - last; last = now
        }
    }
    if (info == null) return
    val cap = if (info.targetFps > 0) "/${info.targetFps}" else ""
    Text(
        "${info.width}\u00D7${info.height} \u00B7 $fps$cap fps",
        color = Color.White, style = MaterialTheme.typography.labelSmall,
        modifier = modifier.background(Color(0x99000000), RoundedCornerShape(8.dp)).padding(horizontal = 8.dp, vertical = 3.dp)
    )
}

/** The PC picture (or a waiting placeholder) with the stats overlay in its top-left corner. */
@Composable
private fun ScreenArea(c: RemoteController, mode: TouchMode, modifier: Modifier, frameModifier: Modifier, waitingModifier: Modifier) {
    val frame = c.frame
    Box(modifier) {
        if (frame != null) ScreenView(
            frame, mode, { c.sendInput(it) }, { _, _ -> }, frameModifier,
            cursor = { if (c.cursorX >= 0f) Offset(c.cursorX, c.cursorY) else null }
        )
        else Box(waitingModifier, contentAlignment = Alignment.Center) { Text("Waiting for the PC screen\u2026", color = Color.White) }
        StreamStatsOverlay(c.streamInfo, c.frameCounter, Modifier.align(Alignment.TopStart).padding(6.dp))
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
    var sensitivity by rememberSaveable { mutableStateOf(1.5f) }
    var showPad by rememberSaveable { mutableStateOf(true) }
    var showKeys by rememberSaveable { mutableStateOf(false) }
    var typeText by rememberSaveable { mutableStateOf("") }
    val send: (JSONObject) -> Unit = { c.sendInput(it) }
    val onSendText: () -> Unit = {
        if (typeText.isNotEmpty()) { send(JSONObject().put("type", "type").put("text", typeText.take(500))); typeText = "" }
    }
    val doubleClick: () -> Unit = { send(JSONObject().put("type", "click").put("count", 2)) }

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val windowWidth = maxWidth
        val windowHeight = maxHeight   // read here: BoxWithConstraints' scope is not reachable from inside Column
        if (maxWidth > maxHeight) {
            // Landscape: PC screen on the left, a separate control panel on the right (nothing is drawn over the picture).
            val panelWidth = (windowWidth * 0.28f).coerceIn(230.dp, 340.dp)
            Row(Modifier.fillMaxSize().background(Color.Black).safeDrawingPadding()) {
                Box(Modifier.weight(1f).fillMaxHeight()) {
                    ScreenArea(c, touchMode, Modifier.fillMaxSize(), Modifier.fillMaxSize(), Modifier.fillMaxSize())
                    if (showKeys) Surface(
                        Modifier.align(Alignment.BottomStart).fillMaxWidth().padding(8.dp),
                        color = MaterialTheme.colorScheme.surface.copy(alpha = 0.93f), shape = RoundedCornerShape(16.dp)
                    ) { Box(Modifier.padding(8.dp)) { KeysPanel(send, typeText, { typeText = it }, onSendText) } }
                    if (!showPad) Row(Modifier.align(Alignment.TopEnd).padding(6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FilledTonalButton(onClick = { showPad = true }, contentPadding = compactPadding) { Text("Trackpad") }
                        FilledTonalButton(onClick = { showKeys = !showKeys }, contentPadding = compactPadding) { Text("Keys") }
                        FilledTonalButton(onClick = { touchMode = touchMode.next() }, contentPadding = compactPadding) { Text("Touch: ${touchMode.label}") }
                        QualityMenuButton(c.quality) { c.setQuality(it) }
                        StopButton { c.stopScreen() }
                    }
                }
                if (showPad) Column(
                    Modifier.width(panelWidth).fillMaxHeight().background(MaterialTheme.colorScheme.surface).padding(8.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        FilledTonalButton(onClick = { touchMode = touchMode.next() }, contentPadding = compactPadding) { Text("Touch: ${touchMode.label}") }
                        FilledTonalButton(onClick = { showKeys = !showKeys }, contentPadding = compactPadding) { Text("Keys") }
                        FilledTonalButton(onClick = { showPad = false }, contentPadding = compactPadding) { Text("Hide") }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        QualityMenuButton(c.quality) { c.setQuality(it) }
                        StopButton { c.stopScreen() }
                    }
                    Trackpad(sensitivity, send, Modifier.weight(1f).fillMaxWidth())
                    PadButtons(send)
                    SpeedRow(sensitivity) { sensitivity = it }
                }
            }
        } else {
            Column(
                Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding().padding(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                SessionToolbar(touchMode, { touchMode = it }, doubleClick, c.quality, { c.setQuality(it) }, { c.stopScreen() })
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
