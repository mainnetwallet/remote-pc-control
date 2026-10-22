package com.mainnetwallet.remotepccontrol

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Bundle
import android.os.SystemClock
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.waitForUpOrCancellation
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.PointerEvent
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // The ViewModel owns the connection, so the session survives rotation (and activity recreation).
        val model = ViewModelProvider(this)[SessionModel::class.java]
        setContent { MaterialTheme { RemotePcApp(model) } }
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

/** What a finger does directly on the PC picture (the trackpad is separate). */
enum class TouchMode(val label: String) {
    OFF("Off"),
    CLICK("Click"),
    MOVE("Move"),
    DRAG("Drag"),
    SCROLL("Scroll")
}

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

/** Connection + session state. Lives in a ViewModel so rotating the phone never drops the session. */
class SessionModel : ViewModel() {
    var baseUrl by mutableStateOf("http://100.64.0.10:8788")
    var token by mutableStateOf("")
    var connected by mutableStateOf(false)
    var message by mutableStateOf("Enter your PC address and API token.")
    var metrics by mutableStateOf<JSONObject?>(null)
    var bitmap by mutableStateOf<Bitmap?>(null)
    var screenOpen by mutableStateOf(false)
    var touchMode by mutableStateOf(TouchMode.OFF)
    var sensitivity by mutableFloatStateOf(2f)     // trackpad pointer speed
    var padVisible by mutableStateOf(true)         // landscape: trackpad panel shown/hidden

    private var screenSocket: WebSocket? = null
    private var inputSocket: WebSocket? = null
    private var generation = 0                      // lets old sockets' late callbacks be ignored

    private fun normalizedBase(): String = baseUrl.trim().trimEnd('/')

    private fun request(path: String, method: String = "GET", body: String? = null, onResult: (Boolean, String) -> Unit) {
        val url = normalizedBase() + path
        val auth = "Bearer " + token.trim()
        viewModelScope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    val builder = Request.Builder().url(url).header("Authorization", auth)
                    if (method == "POST") builder.post((body ?: "{}").toRequestBody("application/json; charset=utf-8".toMediaType()))
                    http.newCall(builder.build()).execute().use { response ->
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
        closeSockets()
        val gen = ++generation
        val wsBase = normalizedBase().replaceFirst("https://", "wss://").replaceFirst("http://", "ws://")
        try {
            screenSocket = wsClient.newWebSocket(Request.Builder().url("$wsBase/ws/screen").build(), object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    webSocket.send(JSONObject().put("token", token.trim()).toString())
                }
                override fun onMessage(webSocket: WebSocket, bytes: okio.ByteString) {
                    if (gen != generation) return
                    val decoded = BitmapFactory.decodeByteArray(bytes.toByteArray(), 0, bytes.size)
                    if (decoded != null) bitmap = decoded
                }
                override fun onMessage(webSocket: WebSocket, text: String) {
                    if (gen == generation && text.contains("\"type\":\"error\"")) message = "Screen stream error: $text"
                }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    if (gen != generation) return
                    message = "Screen stream disconnected: ${t.message ?: "network error"}"
                    closeSession()
                }
            })
            inputSocket = wsClient.newWebSocket(Request.Builder().url("$wsBase/ws/input").build(), object : WebSocketListener() {
                override fun onOpen(webSocket: WebSocket, response: Response) {
                    webSocket.send(JSONObject().put("token", token.trim()).toString())
                }
                override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                    if (gen == generation) message = "Input connection failed: ${t.message ?: "network error"}"
                }
            })
            screenOpen = true
        } catch (e: Exception) {
            message = "Could not open the screen session: ${e.message ?: "invalid URL"}"
            closeSession()
        }
    }

    /** User pressed Stop / Back. */
    fun stopScreen() {
        generation++
        screenSocket?.close(1000, "User closed screen")
        inputSocket?.close(1000, "User closed screen")
        screenSocket = null; inputSocket = null; screenOpen = false; bitmap = null
    }

    private fun closeSockets() {
        generation++
        screenSocket?.cancel(); inputSocket?.cancel()
        screenSocket = null; inputSocket = null
    }

    private fun closeSession() { closeSockets(); screenOpen = false; bitmap = null }

    fun sendInput(o: JSONObject) { inputSocket?.send(o.toString()) }

    override fun onCleared() { closeSockets() }
}

@Composable
private fun RemotePcApp(model: SessionModel) {
    if (model.screenOpen) SessionScreen(model) else HomeScreen(model)
}

@Composable
private fun HomeScreen(model: SessionModel) {
    var showPowerConfirm by rememberSaveable { mutableStateOf<String?>(null) }

    if (showPowerConfirm != null) {
        AlertDialog(
            onDismissRequest = { showPowerConfirm = null },
            title = { Text("Confirm ${showPowerConfirm!!.replaceFirstChar { it.uppercase() }}") },
            text = { Text("This will ${showPowerConfirm} your PC. Continue?") },
            confirmButton = { TextButton(onClick = { val a = showPowerConfirm!!; showPowerConfirm = null; model.power(a) }) { Text("Confirm") } },
            dismissButton = { TextButton(onClick = { showPowerConfirm = null }) { Text("Cancel") } }
        )
    }

    Column(
        Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState()).padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("Remote PC Control", style = MaterialTheme.typography.headlineMedium)
        Text("Connect to your Windows PC through a private Tailscale/WireGuard network.", style = MaterialTheme.typography.bodyMedium)
        OutlinedTextField(value = model.baseUrl, onValueChange = { model.baseUrl = it }, label = { Text("PC URL") }, placeholder = { Text("http://100.64.0.10:8788") }, modifier = Modifier.fillMaxWidth(), singleLine = true)
        OutlinedTextField(value = model.token, onValueChange = { model.token = it }, label = { Text("API token") }, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth(), singleLine = true)
        Button(onClick = { model.connect() }, modifier = Modifier.fillMaxWidth()) { Text(if (model.connected) "Refresh connection" else "Connect to PC") }
        Text(model.message, style = MaterialTheme.typography.bodySmall, color = if (model.connected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant)

        model.metrics?.let { m ->
            Text("PC Status", style = MaterialTheme.typography.titleLarge)
            MetricRow("Computer", m.optString("hostname", "Windows PC"))
            MetricRow("CPU", "${m.optDouble("cpu_percent", 0.0).toInt()}%")
            MetricRow("Memory", "${m.optJSONObject("memory")?.optDouble("percent", 0.0)?.toInt() ?: 0}%")
            MetricRow("Disk", "${m.optJSONObject("disk")?.optDouble("percent", 0.0)?.toInt() ?: 0}%")
            MetricRow("Network received", formatBytes(m.optJSONObject("network")?.optLong("recv_bytes_per_sec") ?: 0L) + "/s")
            MetricRow("Network sent", formatBytes(m.optJSONObject("network")?.optLong("sent_bytes_per_sec") ?: 0L) + "/s")
            OutlinedButton(onClick = { model.connect() }, modifier = Modifier.fillMaxWidth()) { Text("Refresh status") }
            Text("PC Controls", style = MaterialTheme.typography.titleLarge)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                OutlinedButton(onClick = { model.power("lock") }, modifier = Modifier.weight(1f)) { Text("Lock") }
                OutlinedButton(onClick = { model.power("sleep") }, modifier = Modifier.weight(1f)) { Text("Sleep") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                Button(onClick = { showPowerConfirm = "restart" }, modifier = Modifier.weight(1f)) { Text("Restart") }
                Button(onClick = { showPowerConfirm = "shutdown" }, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)) { Text("Shutdown") }
            }
            Text("Live screen & trackpad", style = MaterialTheme.typography.titleLarge)
            Button(onClick = { model.startScreen() }, modifier = Modifier.fillMaxWidth()) { Text("Start screen session") }
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
private val sessionBackground = Color(0xFF202124)

/**
 * Session screen.
 * Portrait: PC picture on top (exact aspect ratio), trackpad + buttons below.
 * Landscape: the PC picture fills the window; the trackpad is a floating panel that can be hidden.
 */
@Composable
private fun SessionScreen(model: SessionModel) {
    var keysOpen by rememberSaveable { mutableStateOf(false) }
    val view = LocalView.current
    DisposableEffect(Unit) { view.keepScreenOn = true; onDispose { view.keepScreenOn = false } }
    BackHandler { model.stopScreen() }

    if (keysOpen) KeysDialog(model) { keysOpen = false }

    BoxWithConstraints(Modifier.fillMaxSize().background(sessionBackground).safeDrawingPadding()) {
        val landscape = maxWidth > maxHeight
        if (landscape) {
            Box(Modifier.fillMaxSize()) {
                ScreenArea(model, Modifier.fillMaxSize())
                if (model.padVisible) {
                    PadPanel(
                        model,
                        Modifier.align(Alignment.BottomEnd).fillMaxWidth(0.42f).fillMaxHeight(0.66f).padding(8.dp)
                            .background(Color(0xD9202124), RoundedCornerShape(16.dp)).padding(8.dp)
                    )
                }
                SessionToolbar(
                    model, landscape = true, onKeys = { keysOpen = true },
                    modifier = Modifier.align(Alignment.TopEnd).padding(6.dp)
                        .background(Color(0xB3202124), RoundedCornerShape(12.dp)).padding(4.dp)
                )
            }
        } else {
            Column(Modifier.fillMaxSize().padding(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                SessionToolbar(model, landscape = false, onKeys = { keysOpen = true }, modifier = Modifier.fillMaxWidth())
                ScreenArea(model, Modifier.fillMaxWidth().heightIn(max = maxHeight * 0.45f))
                PadPanel(model, Modifier.weight(1f).fillMaxWidth())
            }
        }
    }
}

@Composable
private fun SessionToolbar(model: SessionModel, landscape: Boolean, onKeys: () -> Unit, modifier: Modifier = Modifier) {
    val colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)
    Row(modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        OutlinedButton(onClick = { model.stopScreen() }, colors = colors, contentPadding = compactPadding) { Text("Stop") }
        OutlinedButton(onClick = onKeys, colors = colors, contentPadding = compactPadding) { Text("Keys") }
        OutlinedButton(
            onClick = { model.touchMode = TouchMode.values()[(model.touchMode.ordinal + 1) % TouchMode.values().size] },
            colors = colors, contentPadding = compactPadding
        ) { Text("Screen touch: ${model.touchMode.label}") }
        OutlinedButton(
            onClick = { model.sendInput(JSONObject().put("type", "click").put("count", 2)) },
            colors = colors, contentPadding = compactPadding
        ) { Text("Double-click") }
        if (landscape) OutlinedButton(onClick = { model.padVisible = !model.padVisible }, colors = colors, contentPadding = compactPadding) {
            Text(if (model.padVisible) "Hide pad" else "Show pad")
        }
    }
}

@Composable
private fun KeysDialog(model: SessionModel, onClose: () -> Unit) {
    var text by rememberSaveable { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onClose,
        title = { Text("Keys") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                QUICK_KEYS.chunked(3).forEach { rowKeys ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        rowKeys.forEach { (label, json) ->
                            OutlinedButton(onClick = { model.sendInput(JSONObject(json)) }, modifier = Modifier.weight(1f), contentPadding = PaddingValues(horizontal = 4.dp, vertical = 6.dp)) {
                                Text(label, maxLines = 1)
                            }
                        }
                        repeat(3 - rowKeys.size) { Spacer(Modifier.weight(1f)) }
                    }
                }
                OutlinedTextField(value = text, onValueChange = { text = it }, label = { Text("Text to type on PC") }, modifier = Modifier.fillMaxWidth())
                Button(onClick = {
                    if (text.isNotEmpty()) {
                        model.sendInput(JSONObject().put("type", "type").put("text", text.take(500)))
                        text = ""
                    }
                }, modifier = Modifier.fillMaxWidth()) { Text("Send text to PC") }
            }
        },
        confirmButton = { TextButton(onClick = onClose) { Text("Close") } }
    )
}

/** The PC picture at its exact aspect ratio. Only this composable reads the frame, so only it redraws at stream rate. */
@Composable
private fun ScreenArea(model: SessionModel, modifier: Modifier) {
    val frame = model.bitmap
    Box(modifier, contentAlignment = Alignment.Center) {
        if (frame == null) {
            Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).background(Color.Black, RoundedCornerShape(6.dp)), contentAlignment = Alignment.Center) {
                Text("Waiting for the PC screen…", color = Color.White)
            }
        } else {
            DirectTouchScreen(frame, model.touchMode, model::sendInput)
        }
    }
}

/** Trackpad, left/right buttons and the speed slider. */
@Composable
private fun PadPanel(model: SessionModel, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Trackpad(model, Modifier.weight(1f).fillMaxWidth())
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            PadButton("Left", "left", model::sendInput, Modifier.weight(1f))
            PadButton("Right", "right", model::sendInput, Modifier.weight(1f))
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Speed", color = Color.White, style = MaterialTheme.typography.bodySmall)
            Slider(
                value = model.sensitivity, onValueChange = { model.sensitivity = it },
                valueRange = 0.5f..5f, modifier = Modifier.weight(1f).padding(horizontal = 8.dp)
            )
            Text("%.1f".format(model.sensitivity), color = Color.White, style = MaterialTheme.typography.bodySmall)
        }
    }
}

/** Turns [TrackpadEngine] actions into protocol messages (relative to the current pointer, no coordinates). */
private class JsonPadSink(private val send: (JSONObject) -> Unit) : PadSink {
    override fun moveBy(dx: Int, dy: Int) = send(JSONObject().put("type", "rel").put("dx", dx).put("dy", dy))
    override fun button(name: String, down: Boolean) = send(JSONObject().put("type", if (down) "down" else "up").put("button", name))
    override fun click(name: String) = send(JSONObject().put("type", "click").put("button", name))
    override fun scroll(steps: Int) = send(JSONObject().put("type", "scroll").put("dy", steps))
}

@Composable
private fun Trackpad(model: SessionModel, modifier: Modifier = Modifier) {
    val engine = remember(model) { TrackpadEngine(JsonPadSink(model::sendInput)) }
    SideEffect { engine.sensitivity = model.sensitivity }
    // If the pad leaves the screen mid-gesture (panel hidden, session stopped) a held button is released.
    DisposableEffect(engine) { onDispose { engine.cancel() } }
    val shape = RoundedCornerShape(14.dp)
    Box(
        modifier.clip(shape).background(Color.Black).border(1.dp, Color(0xFF4A4A52), shape).trackpadGestures(engine),
        contentAlignment = Alignment.Center
    ) {
        Text("Trackpad", color = Color(0xFF3A3A40), style = MaterialTheme.typography.labelMedium)
    }
}

/** Feeds raw pointer events into [engine], one gesture at a time. All gesture decisions live in the engine. */
private fun Modifier.trackpadGestures(engine: TrackpadEngine): Modifier = pointerInput(engine) {
    engine.slopPx = viewConfiguration.touchSlop
    engine.scrollStepPx = 28.dp.toPx()
    awaitEachGesture {
        val down = awaitFirstDown(requireUnconsumed = false)
        engine.begin(down.uptimeMillis)
        down.consume()
        try {
            while (true) {
                // A held second touch (tap, then press) must become a drag even if the finger never moves.
                val timeout = engine.holdTimeoutMs(SystemClock.uptimeMillis())
                val event: PointerEvent? =
                    if (timeout == null) awaitPointerEvent() else withTimeoutOrNull(timeout) { awaitPointerEvent() }
                if (event == null) { engine.tick(SystemClock.uptimeMillis()); continue }
                val pressed = event.changes.filter { it.pressed }
                val time = event.changes.maxOf { it.uptimeMillis }
                if (pressed.isEmpty()) { engine.end(time); break }
                var sumX = 0f
                var sumY = 0f
                pressed.forEach { val d = it.positionChange(); sumX += d.x; sumY += d.y }
                engine.update(time, pressed.size, sumX / pressed.size, sumY / pressed.size)
                event.changes.forEach { it.consume() }
            }
        } finally {
            engine.cancel()   // no-op after a normal end; sends the button "up" on any abnormal exit
        }
    }
}

/** Mouse button under the pad. Press = down, release/cancel = up, so it can also be held to drag. */
@Composable
private fun PadButton(label: String, button: String, send: (JSONObject) -> Unit, modifier: Modifier = Modifier) {
    var pressed by remember { mutableStateOf(false) }
    val currentSend by rememberUpdatedState(send)
    Box(
        modifier.height(52.dp).clip(RoundedCornerShape(12.dp))
            .background(if (pressed) Color(0xFF55555F) else Color(0xFF2E2E36))
            .pointerInput(button) {
                awaitEachGesture {
                    awaitFirstDown(requireUnconsumed = false)
                    pressed = true
                    currentSend(JSONObject().put("type", "down").put("button", button))
                    try {
                        waitForUpOrCancellation()
                    } finally {
                        pressed = false
                        currentSend(JSONObject().put("type", "up").put("button", button))
                    }
                }
            },
        contentAlignment = Alignment.Center
    ) { Text(label, color = Color.White, style = MaterialTheme.typography.titleMedium) }
}

/**
 * The PC frame with optional direct touch (absolute coordinates, normalized 0..1 of the visible picture).
 * The box is sized to the frame's aspect ratio (no letterbox), so a touch maps 1:1 onto the picture.
 */
@Composable
private fun DirectTouchScreen(frame: Bitmap, mode: TouchMode, send: (JSONObject) -> Unit) {
    fun emit(type: String, p: Offset, size: androidx.compose.ui.unit.IntSize, button: String? = null) {
        if (size.width == 0 || size.height == 0) return
        val nx = (p.x / size.width).coerceIn(0f, 1f).toDouble()
        val ny = (p.y / size.height).coerceIn(0f, 1f).toDouble()
        val o = JSONObject().put("type", type).put("nx", nx).put("ny", ny)
        if (button != null) o.put("button", button)
        send(o)
    }
    Image(
        bitmap = frame.asImageBitmap(),
        contentDescription = "Live Windows desktop",
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
                if (mode == TouchMode.OFF || mode == TouchMode.CLICK) return@pointerInput
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
