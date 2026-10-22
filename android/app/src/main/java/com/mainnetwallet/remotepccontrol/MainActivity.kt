package com.mainnetwallet.remotepccontrol

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.math.abs

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { RemotePcApp() } }
    }
}

private val http = OkHttpClient.Builder()
    .connectTimeout(8, TimeUnit.SECONDS)
    .readTimeout(12, TimeUnit.SECONDS)
    .build()

// Streams can be idle for a while, so no read timeout; pings detect dead connections instead.
private val wsClient = http.newBuilder()
    .readTimeout(0, TimeUnit.MILLISECONDS)
    .pingInterval(20, TimeUnit.SECONDS)
    .build()

private enum class TouchMode(val label: String, val hint: String) {
    OFF("Off", "Screen is view-only; use the trackpad"),
    CLICK("Click", "Tap = click · long-press = right click"),
    MOVE("Move", "Drag to move the pointer without clicking"),
    DRAG("Drag", "Drag = hold the left button (select, move windows)"),
    SCROLL("Scroll", "Drag up/down to scroll the page")
}

private fun TouchMode.next(): TouchMode = TouchMode.values().let { it[(ordinal + 1) % it.size] }

private val QUICK_KEYS = listOf(
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
private fun RemotePcApp() {
    var baseUrl by remember { mutableStateOf("http://100.64.0.10:8788") }
    var token by remember { mutableStateOf("") }
    var connected by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Enter your PC address and API token.") }
    var metrics by remember { mutableStateOf<JSONObject?>(null) }
    var bitmap by remember { mutableStateOf<Bitmap?>(null) }
    var screenOpen by remember { mutableStateOf(false) }
    var showPowerConfirm by remember { mutableStateOf<String?>(null) }
    var typeText by rememberSaveable { mutableStateOf("") }
    var touchMode by remember { mutableStateOf(TouchMode.OFF) }
    // Plain UI preferences survive recreation; the sockets/bitmap survive rotation because the activity is not recreated (manifest configChanges).
    var sensitivity by rememberSaveable { mutableStateOf(1.5f) }
    var showPad by rememberSaveable { mutableStateOf(true) }
    var showKeys by rememberSaveable { mutableStateOf(false) }
    var screenSocket by remember { mutableStateOf<WebSocket?>(null) }
    var inputSocket by remember { mutableStateOf<WebSocket?>(null) }
    val scope = rememberCoroutineScope()

    fun normalizedBase(): String = baseUrl.trim().trimEnd('/')

    fun request(path: String, method: String = "GET", body: String? = null, onResult: (Boolean, String) -> Unit) {
        val url = normalizedBase() + path
        val requestBuilder = Request.Builder().url(url).header("Authorization", "Bearer " + token.trim())
        if (method == "POST") requestBuilder.post((body ?: "{}").toRequestBody("application/json; charset=utf-8".toMediaType()))
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    http.newCall(requestBuilder.build()).execute().use { response ->
                        val text = response.body?.string().orEmpty()
                        response.isSuccessful to (text.ifBlank { if (response.isSuccessful) "Success" else "HTTP ${response.code}" })
                    }
                } catch (e: Exception) { false to (e.message ?: "Connection failed") }
            }
            onResult(result.first, result.second)
        }
    }

    fun connect() {
        if (normalizedBase().isBlank() || token.isBlank()) { message = "PC URL and API token are required."; return }
        request("/api/v1/status") { ok, text ->
            connected = ok
            message = if (ok) "Connected securely over your private network." else "Connection failed: $text"
            if (ok) try { metrics = JSONObject(text) } catch (_: Exception) { metrics = null }
        }
    }

    fun power(action: String) {
        request("/api/v1/control/$action", "POST", if (action == "restart" || action == "shutdown") "{\"confirm\":true}" else "{}") { ok, text ->
            message = if (ok) "${action.replaceFirstChar { it.uppercase() }} request sent." else "Action failed: $text"
        }
    }

    fun startScreen() {
        if (!connected) { message = "Connect to the PC first."; return }
        val wsBase = normalizedBase().replaceFirst("https://", "wss://").replaceFirst("http://", "ws://")
        screenOpen = true
        val screenReq = Request.Builder().url("$wsBase/ws/screen").build()
        screenSocket = wsClient.newWebSocket(screenReq, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                webSocket.send(JSONObject().put("token", token.trim()).toString())
            }
            override fun onMessage(webSocket: WebSocket, bytes: okio.ByteString) {
                val decoded = BitmapFactory.decodeByteArray(bytes.toByteArray(), 0, bytes.size)
                if (decoded != null) bitmap = decoded
            }
            override fun onMessage(webSocket: WebSocket, text: String) {
                if (text.contains("\"type\":\"error\"")) message = "Screen stream error: $text"
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                message = "Screen stream disconnected: ${t.message ?: "network error"}"
                screenOpen = false
            }
        })
        val inputReq = Request.Builder().url("$wsBase/ws/input").build()
        inputSocket = wsClient.newWebSocket(inputReq, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                webSocket.send(JSONObject().put("token", token.trim()).toString())
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                message = "Input connection failed: ${t.message ?: "network error"}"
            }
        })
    }

    fun stopScreen() {
        screenSocket?.close(1000, "User closed screen")
        inputSocket?.close(1000, "User closed screen")
        screenSocket = null; inputSocket = null; screenOpen = false; bitmap = null
    }

    fun sendInput(o: JSONObject) { inputSocket?.send(o.toString()) }

    fun sendText() {
        if (typeText.isNotEmpty()) { sendInput(JSONObject().put("type", "type").put("text", typeText.take(500))); typeText = "" }
    }

    val view = LocalView.current
    DisposableEffect(screenOpen) { view.keepScreenOn = screenOpen; onDispose { view.keepScreenOn = false } }
    DisposableEffect(Unit) { onDispose { screenSocket?.cancel(); inputSocket?.cancel() } }

    if (showPowerConfirm != null) {
        AlertDialog(
            onDismissRequest = { showPowerConfirm = null },
            title = { Text("Confirm ${showPowerConfirm!!.replaceFirstChar { it.uppercase() }}") },
            text = { Text("This will ${showPowerConfirm} your PC. Continue?") },
            confirmButton = { TextButton(onClick = { val a = showPowerConfirm!!; showPowerConfirm = null; power(a) }) { Text("Confirm") } },
            dismissButton = { TextButton(onClick = { showPowerConfirm = null }) { Text("Cancel") } }
        )
    }

    if (screenOpen) {
        SessionScreen(
            frame = bitmap, touchMode = touchMode, onMode = { touchMode = it }, send = ::sendInput,
            sensitivity = sensitivity, onSensitivity = { sensitivity = it },
            showPad = showPad, onShowPad = { showPad = it },
            showKeys = showKeys, onShowKeys = { showKeys = it },
            typeText = typeText, onTypeText = { typeText = it }, onSendText = { sendText() },
            onStop = { stopScreen() }
        )
    } else Column(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState()).padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Remote PC Control", style = MaterialTheme.typography.headlineMedium)
        Text("Connect to your Windows PC through a private Tailscale/WireGuard network.", style = MaterialTheme.typography.bodyMedium)
        OutlinedTextField(value = baseUrl, onValueChange = { baseUrl = it }, label = { Text("PC URL") }, placeholder = { Text("http://100.64.0.10:8788") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(value = token, onValueChange = { token = it }, label = { Text("API token") }, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(), singleLine = true)
        Button(onClick = { connect() }, modifier = Modifier.fillMaxWidth()) { Text(if (connected) "Refresh connection" else "Connect to PC") }
        Text(message, style = MaterialTheme.typography.bodySmall, color = if (connected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)

        metrics?.let { m ->
            Text("PC Status", style = MaterialTheme.typography.titleLarge)
            MetricRow("Computer", m.optString("hostname", "Windows PC"))
            MetricRow("CPU", "${m.optDouble("cpu_percent", 0.0).toInt()}%")
            MetricRow("Memory", "${m.optJSONObject("memory")?.optDouble("percent", 0.0)?.toInt() ?: 0}%")
            MetricRow("Disk", "${m.optJSONObject("disk")?.optDouble("percent", 0.0)?.toInt() ?: 0}%")
            MetricRow("Network received", formatBytes(m.optJSONObject("network")?.optLong("recv_bytes_per_sec") ?: 0L) + "/s")
            MetricRow("Network sent", formatBytes(m.optJSONObject("network")?.optLong("sent_bytes_per_sec") ?: 0L) + "/s")
            OutlinedButton(onClick = { connect() }, modifier = Modifier.fillMaxWidth()) { Text("Refresh status") }
            Text("PC Controls", style = MaterialTheme.typography.titleLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(onClick = { power("lock") }, modifier = Modifier.weight(1f)) { Text("Lock") }
                OutlinedButton(onClick = { power("sleep") }, modifier = Modifier.weight(1f)) { Text("Sleep") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                Button(onClick = { showPowerConfirm = "restart" }, modifier = Modifier.weight(1f)) { Text("Restart") }
                Button(onClick = { showPowerConfirm = "shutdown" }, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) { Text("Shutdown") }
            }
            Text("Live screen & touch control", style = MaterialTheme.typography.titleLarge)
            Button(onClick = { startScreen() }, modifier = Modifier.fillMaxWidth()) { Text("Start screen session") }
        }
        Text("Security: never port-forward the PC agent. The token is held in app memory only. Screen/input control works only in the logged-in desktop session.", style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun MetricRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp)).padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label)
        Text(value, style = MaterialTheme.typography.titleMedium)
    }
}

private fun formatBytes(value: Long): String = when {
    value >= 1024L * 1024L -> String.format("%.1f MB", value / (1024.0 * 1024.0))
    value >= 1024L -> String.format("%.1f KB", value / 1024.0)
    else -> "$value B"
}

private val compactPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)

@Composable
private fun ModeBar(mode: TouchMode, onMode: (TouchMode) -> Unit, onDoubleClick: () -> Unit, extraLabel: String, onExtra: () -> Unit) {
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        TouchMode.values().forEach { m ->
            if (m == mode) Button(onClick = { onMode(m) }, contentPadding = compactPadding) { Text(m.label) }
            else OutlinedButton(onClick = { onMode(m) }, contentPadding = compactPadding) { Text(m.label) }
        }
        OutlinedButton(onClick = onDoubleClick, contentPadding = compactPadding) { Text("Double-click") }
        OutlinedButton(onClick = onExtra, contentPadding = compactPadding) { Text(extraLabel) }
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

/**
 * Shows the PC frame and turns touches into mouse input.
 * Coordinates are sent normalized (0..1 of the visible picture), so they stay correct whatever
 * size the frame is scaled to. The box is sized to the frame's aspect ratio (no letterbox),
 * so a touch maps 1:1 onto the picture.
 */
@Composable
private fun ScreenView(frame: Bitmap, mode: TouchMode, send: (JSONObject) -> Unit, onPosition: (Double, Double) -> Unit, modifier: Modifier = Modifier) {
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
            bitmap = frame.asImageBitmap(),
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
        )
    }
}

private const val TAP_TIMEOUT_MS = 300L          // finger down -> up shorter than this is a tap
private const val DOUBLE_TAP_WINDOW_MS = 300L    // a touch this soon after a tap is a double tap / tap-then-slide
private const val MOVE_INTERVAL_MS = 16L         // about 60 pointer updates per second
private const val MAX_REL_STEP = 500             // the server clamps "rel" to +-500 per message
private const val PAD_PC_PX_PER_DP = 2f          // PC pixels per dp of finger travel at speed 1.0

/**
 * Laptop-style trackpad (plain black surface, no picture of the PC).
 *  one finger slide = relative move, tap = left click, second tap soon after = double click,
 *  tap then slide = drag (left button held), two-finger tap = right click, two-finger slide = scroll.
 * Taps are sent as plain clicks at the current pointer; two quick taps become a double click on the PC.
 */
@Composable
private fun Trackpad(sensitivity: Float, send: (JSONObject) -> Unit, modifier: Modifier = Modifier) {
    val sendNow by rememberUpdatedState(send)
    val speedNow by rememberUpdatedState(sensitivity)
    val shape = RoundedCornerShape(14.dp)
    Box(
        modifier.background(Color.Black, shape).border(1.dp, Color(0xFF3A3A3A), shape)
            .pointerInput(Unit) {
                var lastTapUpMs = 0L   // survives between gestures (needed for double tap / tap-then-slide)
                val slop = viewConfiguration.touchSlop
                val scrollStepPx = 14.dp.toPx()
                awaitEachGesture {
                    val first = awaitFirstDown(requireUnconsumed = false)
                    val downMs = first.uptimeMillis
                    val tapDrag = lastTapUpMs != 0L && downMs - lastTapUpMs <= DOUBLE_TAP_WINDOW_MS
                    lastTapUpMs = 0L
                    var maxPointers = 1
                    var prevPressed = 1
                    var releaseMs = 0L
                    var moved = false        // one finger went past touch slop
                    var scrolled = false     // two fingers went past touch slop
                    var dragging = false     // left button is held down
                    var pendingX = 0f; var pendingY = 0f
                    var scrollX = 0f; var scrollY = 0f
                    var twoX = 0f; var twoY = 0f
                    var lastSendMs = 0L

                    fun flush(force: Boolean) {
                        val t = System.nanoTime() / 1_000_000L
                        if (!force && t - lastSendMs < MOVE_INTERVAL_MS) return
                        val ix = pendingX.toInt().coerceIn(-MAX_REL_STEP, MAX_REL_STEP)
                        val iy = pendingY.toInt().coerceIn(-MAX_REL_STEP, MAX_REL_STEP)
                        if (ix == 0 && iy == 0) return
                        pendingX -= ix; pendingY -= iy; lastSendMs = t
                        sendNow(JSONObject().put("type", "rel").put("dx", ix).put("dy", iy))
                    }

                    try {
                        while (true) {
                            // While a throttled move is waiting, wake up on a timer so the last bit is not held back.
                            val waiting = moved && (abs(pendingX) >= 1f || abs(pendingY) >= 1f)
                            val event = if (waiting) withTimeoutOrNull(MOVE_INTERVAL_MS) { awaitPointerEvent() } else awaitPointerEvent()
                            if (event == null) { flush(true); continue }
                            val pressed = event.changes.filter { it.pressed }
                            if (pressed.size > maxPointers) maxPointers = pressed.size
                            if (pressed.size < prevPressed && releaseMs == 0L) releaseMs = event.changes.maxOf { it.uptimeMillis }
                            prevPressed = pressed.size
                            if (pressed.isEmpty()) break

                            if (maxPointers == 1) {
                                val c = pressed[0]
                                val d = c.positionChange()
                                val pxToPc = speedNow * PAD_PC_PX_PER_DP / density
                                pendingX += d.x * pxToPc; pendingY += d.y * pxToPc
                                if (!moved && (c.position - first.position).getDistance() > slop) {
                                    moved = true
                                    if (tapDrag) { dragging = true; sendNow(JSONObject().put("type", "down").put("button", "left")) }
                                }
                                if (moved) flush(false)
                            } else if (maxPointers == 2 && pressed.size == 2) {
                                var sx = 0f; var sy = 0f
                                pressed.forEach { val d = it.positionChange(); sx += d.x; sy += d.y }
                                sx /= 2f; sy /= 2f
                                twoX += sx; twoY += sy
                                scrollX += sx; scrollY += sy
                                if (!scrolled && Offset(twoX, twoY).getDistance() > slop) scrolled = true
                                if (scrolled) {
                                    val stepsX = (scrollX / scrollStepPx).toInt()
                                    val stepsY = (scrollY / scrollStepPx).toInt()
                                    if (stepsX != 0 || stepsY != 0) {
                                        scrollX -= stepsX * scrollStepPx; scrollY -= stepsY * scrollStepPx
                                        // Content follows the fingers: fingers down -> wheel up (dy > 0); fingers right -> dx < 0.
                                        sendNow(JSONObject().put("type", "scroll").put("dx", -stepsX).put("dy", stepsY))
                                    }
                                }
                            }   // three or more fingers: ignored
                            event.changes.forEach { if (it.positionChange() != Offset.Zero) it.consume() }
                        }

                        val heldMs = (if (releaseMs != 0L) releaseMs else downMs) - downMs
                        if (dragging) {
                            flush(true)
                            sendNow(JSONObject().put("type", "up").put("button", "left")); dragging = false
                        } else if (maxPointers == 1) {
                            if (moved) flush(true)
                            else if (heldMs <= TAP_TIMEOUT_MS) {
                                sendNow(JSONObject().put("type", "click").put("button", "left"))
                                if (!tapDrag) lastTapUpMs = releaseMs
                            }
                        } else if (maxPointers == 2 && !scrolled && heldMs <= TAP_TIMEOUT_MS) {
                            sendNow(JSONObject().put("type", "click").put("button", "right"))
                        }
                    } finally {
                        // Cancelled mid-drag (pad hidden, session stopped...): never leave the button stuck down.
                        if (dragging) sendNow(JSONObject().put("type", "up").put("button", "left"))
                    }
                }
            },
        contentAlignment = Alignment.Center
    ) {
        Text("Trackpad", color = Color(0xFF5A5A5A), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun PadButtons(
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
private fun SpeedRow(sensitivity: Float, onSensitivity: (Float) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text("Speed", style = MaterialTheme.typography.bodySmall)
        Slider(value = sensitivity, onValueChange = onSensitivity, valueRange = 0.5f..3f, modifier = Modifier.weight(1f).padding(horizontal = 8.dp))
        Text(String.format("%.1fx", sensitivity), style = MaterialTheme.typography.bodySmall)
    }
}

@Composable
private fun KeysPanel(send: (JSONObject) -> Unit, typeText: String, onTypeText: (String) -> Unit, onSendText: () -> Unit) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        QuickKeyBar(send)
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            OutlinedTextField(value = typeText, onValueChange = onTypeText, label = { Text("Text to type on PC") }, modifier = Modifier.weight(1f), singleLine = true)
            Button(onClick = onSendText) { Text("Send") }
        }
    }
}

/**
 * Full-window session UI.
 * Portrait: PC screen on top (exact aspect ratio), trackpad below.
 * Landscape: PC screen fills the window; the trackpad (and keys) are hideable panels on top of it.
 */
@Composable
private fun SessionScreen(
    frame: Bitmap?, touchMode: TouchMode, onMode: (TouchMode) -> Unit, send: (JSONObject) -> Unit,
    sensitivity: Float, onSensitivity: (Float) -> Unit,
    showPad: Boolean, onShowPad: (Boolean) -> Unit,
    showKeys: Boolean, onShowKeys: (Boolean) -> Unit,
    typeText: String, onTypeText: (String) -> Unit, onSendText: () -> Unit,
    onStop: () -> Unit
) {
    val doubleClick: () -> Unit = { send(JSONObject().put("type", "click").put("count", 2)) }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        if (maxWidth > maxHeight) {
            Box(Modifier.fillMaxSize().background(Color.Black).safeDrawingPadding()) {
                if (frame != null) ScreenView(frame, touchMode, send, { _, _ -> }, Modifier.fillMaxSize())
                else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text("Waiting for the PC screen…", color = Color.White) }
                Row(Modifier.align(Alignment.TopEnd).padding(6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilledTonalButton(onClick = { onShowPad(!showPad) }, contentPadding = compactPadding) { Text(if (showPad) "Hide pad" else "Trackpad") }
                    FilledTonalButton(onClick = { onShowKeys(!showKeys) }, contentPadding = compactPadding) { Text("Keys") }
                    FilledTonalButton(onClick = { onMode(touchMode.next()) }, contentPadding = compactPadding) { Text("Touch: ${touchMode.label}") }
                    Button(onClick = onStop, contentPadding = compactPadding) { Text("Stop") }
                }
                if (showKeys) Surface(
                    Modifier.align(Alignment.BottomStart).fillMaxWidth(if (showPad) 0.56f else 1f).padding(8.dp),
                    color = MaterialTheme.colorScheme.surface.copy(alpha = 0.93f), shape = RoundedCornerShape(16.dp)
                ) { Box(Modifier.padding(8.dp)) { KeysPanel(send, typeText, onTypeText, onSendText) } }
                if (showPad) Surface(
                    Modifier.align(Alignment.BottomEnd).fillMaxHeight(0.8f).fillMaxWidth(0.4f).padding(8.dp),
                    color = MaterialTheme.colorScheme.surface.copy(alpha = 0.93f), shape = RoundedCornerShape(16.dp)
                ) {
                    Column(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Trackpad(sensitivity, send, Modifier.weight(1f).fillMaxWidth())
                        PadButtons(send)
                        SpeedRow(sensitivity, onSensitivity)
                    }
                }
            }
        } else {
            Column(
                Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background).safeDrawingPadding().padding(8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                ModeBar(touchMode, onMode, doubleClick, "Stop", onStop)
                if (frame != null) ScreenView(frame, touchMode, send, { _, _ -> }, Modifier.fillMaxWidth())
                else Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).background(Color.Black, RoundedCornerShape(6.dp)), contentAlignment = Alignment.Center) {
                    Text("Waiting for the PC screen…", color = Color.White)
                }
                Trackpad(sensitivity, send, Modifier.weight(1f).fillMaxWidth().heightIn(min = 120.dp))
                PadButtons(send, showKeys = showKeys, onShowKeys = onShowKeys)
                SpeedRow(sensitivity, onSensitivity)
                if (showKeys) KeysPanel(send, typeText, onTypeText, onSendText)
            }
        }
    }
}
