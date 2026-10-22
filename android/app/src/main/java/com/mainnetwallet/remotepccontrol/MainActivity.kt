package com.mainnetwallet.remotepccontrol

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
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
        screenSocket = http.newWebSocket(screenReq, object : WebSocketListener() {
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
        inputSocket = http.newWebSocket(inputReq, object : WebSocketListener() {
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
                bitmap?.let { frame ->
                    Image(
                        bitmap = frame.asImageBitmap(),
                        contentDescription = "Live Windows desktop. Tap to move the mouse and click.",
                        modifier = Modifier.fillMaxWidth().heightIn(max = 520.dp)
                            .background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(8.dp))
                            .pointerInput(frame, inputSocket) {
                                detectTapGestures { p ->
                                    val x = (p.x / size.width * frame.width).toInt().coerceIn(0, frame.width - 1)
                                    val y = (p.y / size.height * frame.height).toInt().coerceIn(0, frame.height - 1)
                                    inputSocket?.send(JSONObject().put("type", "move").put("x", x).put("y", y).toString())
                                    inputSocket?.send(JSONObject().put("type", "click").toString())
                                }
                            }
                    )
                    Text("Tap the screen to click. Keyboard input is available below.", style = MaterialTheme.typography.bodySmall)
                } ?: Text("Waiting for the PC screen…")
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
