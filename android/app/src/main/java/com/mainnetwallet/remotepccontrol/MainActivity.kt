package com.mainnetwallet.remotepccontrol

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.compose.ui.input.pointer.pointerInput
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
    CLICK("Click", "Tap = click · long-press = right click"),
    MOVE("Move", "Drag to move the pointer without clicking"),
    DRAG("Drag", "Drag = hold the left button (select, move windows)"),
    SCROLL("Scroll", "Drag up/down to scroll the page")
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
    var typeText by remember { mutableStateOf("") }
    var touchMode by remember { mutableStateOf(TouchMode.CLICK) }
    var showFullscreen by remember { mutableStateOf(false) }
    var lastNx by remember { mutableStateOf(0.5) }
    var lastNy by remember { mutableStateOf(0.5) }
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

    val view = LocalView.current
    DisposableEffect(screenOpen) { view.keepScreenOn = screenOpen; onDispose { view.keepScreenOn = false } }
    DisposableEffect(Unit) { onDispose { screenSocket?.cancel(); inputSocket?.cancel() } }

    if (showFullscreen && screenOpen) {
        Dialog(onDismissRequest = { showFullscreen = false }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
            Surface(Modifier.fillMaxSize(), color = Color.Black) {
                Column(Modifier.fillMaxSize().padding(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    ModeBar(touchMode, { touchMode = it }, { sendInput(JSONObject().put("type", "click").put("count", 2).put("nx", lastNx).put("ny", lastNy)) }, "Close") { showFullscreen = false }
                    val f = bitmap
                    if (f != null) ScreenView(f, touchMode, ::sendInput, { x, y -> lastNx = x; lastNy = y }, Modifier.weight(1f).fillMaxWidth())
                    else Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) { Text("Waiting for the PC screen…", color = Color.White) }
                    QuickKeyBar(::sendInput)
                }
            }
        }
    }

    if (showPowerConfirm != null) {
        AlertDialog(
            onDismissRequest = { showPowerConfirm = null },
            title = { Text("Confirm ${showPowerConfirm!!.replaceFirstChar { it.uppercase() }}") },
            text = { Text("This will ${showPowerConfirm} your PC. Continue?") },
            confirmButton = { TextButton(onClick = { val a = showPowerConfirm!!; showPowerConfirm = null; power(a) }) { Text("Confirm") } },
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
            if (!screenOpen) Button(onClick = { startScreen() }, modifier = Modifier.fillMaxWidth()) { Text("Start screen session") }
            else {
                OutlinedButton(onClick = { stopScreen() }, modifier = Modifier.fillMaxWidth()) { Text("Stop screen session") }
                ModeBar(touchMode, { touchMode = it }, { sendInput(JSONObject().put("type", "click").put("count", 2).put("nx", lastNx).put("ny", lastNy)) }, "Fullscreen") { showFullscreen = true }
                bitmap?.let { frame ->
                    ScreenView(frame, touchMode, ::sendInput, { x, y -> lastNx = x; lastNy = y }, Modifier.fillMaxWidth())
                    Text(touchMode.hint, style = MaterialTheme.typography.bodySmall)
                } ?: Text("Waiting for the PC screen…")
                QuickKeyBar(::sendInput)
                OutlinedTextField(value = typeText, onValueChange = { typeText = it }, label = { Text("Text to type on PC") }, modifier = Modifier.fillMaxWidth())
                Button(onClick = {
                    if (typeText.isNotEmpty()) {
                        inputSocket?.send(JSONObject().put("type", "type").put("text", typeText.take(500)).toString())
                        typeText = ""
                    }
                }, modifier = Modifier.fillMaxWidth()) { Text("Send text to PC") }
            }
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
                    if (mode == TouchMode.CLICK) return@pointerInput
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
