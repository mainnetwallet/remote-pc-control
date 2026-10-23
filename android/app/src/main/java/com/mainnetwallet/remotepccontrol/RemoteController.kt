package com.mainnetwallet.remotepccontrol

import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

private val http = OkHttpClient.Builder()
    .connectTimeout(8, TimeUnit.SECONDS)
    .readTimeout(12, TimeUnit.SECONDS)
    .build()

// Streams can be idle for a while, so no read timeout; pings detect dead connections instead.
private val wsClient = http.newBuilder()
    .readTimeout(0, TimeUnit.MILLISECONDS)
    .pingInterval(20, TimeUnit.SECONDS)
    .build()

private const val DEFAULT_URL = "gist:b1b39edd1c382e1a39a3156293d3eba1"
private const val PREF_TOKEN = "pc_token_enc"   // password, encrypted with an Android Keystore key (see SecureStore)
private const val PREF_URL = "pc_url"        // the token is never stored, only the address
private const val PREF_QUALITY = "quality"
private const val LOCAL_CURSOR_NS = 250_000_000L   // after the finger moved the pointer, trust our own prediction this long

/** Live-screen quality presets. Each one is sent to the PC as {"type":"config","max_width","fps","quality"}. */
enum class Quality(val label: String, val maxWidth: Int, val fps: Int, val jpeg: Int, val hint: String) {
    LOW("Low", 960, 20, 45, "960 px wide, up to 20 fps. Saves data."),
    MEDIUM("Medium", 1280, 30, 65, "1280 px wide, up to 30 fps."),
    HIGH("High", 1920, 30, 78, "1920 px wide, up to 30 fps."),
    NATIVE("Native", 0, 20, 85, "The PC's full resolution, up to 20 fps. Needs a fast link.");

    fun configMessage(): String = JSONObject()
        .put("type", "config").put("max_width", maxWidth).put("fps", fps).put("quality", jpeg)
        .put("cursor", true)   // the app draws the pointer itself: frames come without it (older PCs ignore this)
        .toString()
}

class Notice(val text: String, val isError: Boolean)

/** What the PC reports from /api/v1/status. */
class PcStatus(
    val hostname: String, val uptimeSeconds: Long,
    val cpu: Int, val memory: Int, val disk: Int,
    val memUsed: Long, val memTotal: Long, val diskUsed: Long, val diskTotal: Long,
    val rxPerSec: Long, val txPerSec: Long
) {
    companion object {
        fun parse(text: String): PcStatus? = try {
            val m = JSONObject(text)
            val mem = m.optJSONObject("memory"); val disk = m.optJSONObject("disk"); val net = m.optJSONObject("network")
            PcStatus(
                hostname = m.optString("hostname", "Windows PC"), uptimeSeconds = m.optLong("uptime_seconds", 0L),
                cpu = m.optDouble("cpu_percent", 0.0).toInt(),
                memory = mem?.optDouble("percent", 0.0)?.toInt() ?: 0, disk = disk?.optDouble("percent", 0.0)?.toInt() ?: 0,
                memUsed = mem?.optLong("used", 0L) ?: 0L, memTotal = mem?.optLong("total", 0L) ?: 0L,
                diskUsed = disk?.optLong("used", 0L) ?: 0L, diskTotal = disk?.optLong("total", 0L) ?: 0L,
                rxPerSec = net?.optLong("recv_bytes_per_sec", 0L) ?: 0L, txPerSec = net?.optLong("sent_bytes_per_sec", 0L) ?: 0L
            )
        } catch (_: Exception) { null }
    }
}

/** Size of the frames being received and the frame-rate cap the PC applies (0 = unknown, older PC agent). */
class StreamInfo(val width: Int, val height: Int, val targetFps: Int)

/**
 * All connection state and networking. UI reads the Compose state properties; the activity is not
 * recreated on rotation (manifest configChanges), so sockets and frames survive it.
 */
class RemoteController(private val scope: CoroutineScope, private val prefs: SharedPreferences) {
    var baseUrl by mutableStateOf(prefs.getString(PREF_URL, DEFAULT_URL) ?: DEFAULT_URL)
    var token by mutableStateOf(prefs.getString(PREF_TOKEN, null)?.let { SecureStore.decrypt(it) } ?: "")
    /** True while the app signs in by itself with the saved password right after start. */
    var restoring by mutableStateOf(false)
        private set
    var connected by mutableStateOf(false)
        private set
    var busy by mutableStateOf(false)
        private set
    var reachable by mutableStateOf(true)
        private set
    var notice by mutableStateOf(Notice("Enter your PC address and API token.", false))
        private set
    var status by mutableStateOf<PcStatus?>(null)
        private set
    var screenOpen by mutableStateOf(false)
        private set
    var frame by mutableStateOf<Bitmap?>(null)
        private set
    var streamInfo by mutableStateOf<StreamInfo?>(null)
        private set
    var quality by mutableStateOf(Quality.values().firstOrNull { it.name == prefs.getString(PREF_QUALITY, null) } ?: Quality.MEDIUM)
        private set

    /**
     * Pointer position as 0..1 of the PC screen (-1 = unknown). The PC streams it on the small input socket and the
     * trackpad moves it at once, so the pointer follows the finger without waiting for a screen frame.
     */
    var cursorX by mutableFloatStateOf(-1f)
        private set
    var cursorY by mutableFloatStateOf(-1f)
        private set
    private var pcWidth = 0
    private var pcHeight = 0
    private var cursorFromServer = false   // only predict locally when the PC really streams the pointer
    private var localCursorUntilNs = 0L

    /** Counts received frames; the session overlay turns it into frames per second. */
    val frameCounter = AtomicInteger()

    private var screenSocket: WebSocket? = null
    private var inputSocket: WebSocket? = null
    private var sessionGen = 0   // callbacks of an older session must not touch the current one

    // When the address field holds a Gist reference ("gist:<id>"), this is the current tunnel URL read from it.
    private var resolvedBase: String? = null

    private fun gistId(input: String): String? =
        Regex("""^(?:gist:|https?://gist\.github\.com/(?:[^/]+/)?)([0-9a-fA-F]{20,40})/?$""").find(input.trim())?.groupValues?.get(1)

    private fun normalizedBase(): String {
        val raw = (if (gistId(baseUrl) != null) resolvedBase.orEmpty() else baseUrl).trim().trimEnd('/')
        return if (raw.isEmpty() || "://" in raw) raw else "http://$raw"
    }

    /** Reads the PC's current link from the secret Gist (file pc-url.txt) that start.ps1 keeps updated. */
    private fun resolveGist(onDone: (String?) -> Unit) {
        val id = gistId(baseUrl)
        if (id == null) { resolvedBase = null; onDone(null); return }
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
                    val req = Request.Builder().url("https://api.github.com/gists/$id")
                        .header("Accept", "application/vnd.github+json").build()
                    http.newCall(req).execute().use { r ->
                        if (!r.isSuccessful) return@use null to "Could not read the Gist (HTTP ${r.code})"
                        val files = JSONObject(r.body?.string().orEmpty()).getJSONObject("files")
                        val url = files.optJSONObject("pc-url.txt")?.optString("content").orEmpty().trim()
                        if (url.startsWith("https://")) url to null else null to "Gist has no PC link yet. Is start.ps1 running?"
                    }
                } catch (e: Exception) { null to ("Could not read the Gist: " + (e.message ?: "network error")) }
            }
            resolvedBase = result.first
            onDone(result.second)
        }
    }

    private fun call(path: String, method: String = "GET", body: String? = null, onResult: (Boolean, String) -> Unit) {
        val builder = try {
            Request.Builder().url(normalizedBase() + path).header("Authorization", "Bearer " + token.trim())
        } catch (_: IllegalArgumentException) { onResult(false, "Invalid PC URL or token format"); return }
        if (method == "POST") builder.post((body ?: "{}").toRequestBody("application/json; charset=utf-8".toMediaType()))
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                try {
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
        if (busy) return
        if (baseUrl.isBlank() || token.isBlank()) { restoring = false; notice = Notice("PC URL and password are required.", true); return }
        busy = true
        resolveGist { gistError ->
            if (gistError != null) { busy = false; restoring = false; connected = false; reachable = false; notice = Notice(gistError, true); return@resolveGist }
            call("/api/v1/status") { ok, text ->
                busy = false; restoring = false
                connected = ok; reachable = ok
                if (ok) {
                    status = PcStatus.parse(text)
                    // Remember the login: the next start signs in by itself until the user taps Log out.
                    prefs.edit().putString(PREF_URL, baseUrl.trim()).putString(PREF_TOKEN, SecureStore.encrypt(token.trim())).apply()
                    notice = Notice("", false)
                } else if (text.contains("Invalid token")) {
                    forgetLogin()
                    notice = Notice("Wrong password. Please log in again.", true)
                } else notice = Notice("Connection failed: $text", true)
            }
        }
    }

    /** Signs in by itself with the saved password (called once at app start). */
    fun autoConnect() {
        if (connected || busy || token.isBlank() || baseUrl.isBlank()) return
        restoring = true
        connect()
    }

    private fun forgetLogin() {
        prefs.edit().remove(PREF_TOKEN).apply()
        token = ""
    }

    /** Quietly reloads the metrics; used by the dashboard's timer. */
    fun refreshStatus() {
        if (!connected) return
        call("/api/v1/status") { ok, text ->
            reachable = ok
            if (ok) PcStatus.parse(text)?.let { status = it }
            else if (text.contains("Invalid token")) disconnect()   // the password was changed on the PC
        }
    }

    fun disconnect() {
        stopScreen()
        connected = false; status = null; reachable = true
        forgetLogin()
        notice = Notice("Logged out.", false)
    }

    fun power(action: PowerAction) {
        call("/api/v1/control/${action.path}", "POST", action.body) { ok, text ->
            notice = if (ok) Notice("${action.label} request sent.", false) else Notice("${action.label} failed: $text", true)
        }
    }

    // The `quality` property's private setter is also named setQuality(Quality) on the JVM; rename this one there.
    @JvmName("applyQuality")
    fun setQuality(q: Quality) {
        quality = q
        prefs.edit().putString(PREF_QUALITY, q.name).apply()
        screenSocket?.send(q.configMessage())   // applied live, the PC answers with the new frame size
    }

    fun startScreen() {
        if (!connected || screenOpen) return
        val gen = ++sessionGen
        val wsBase = normalizedBase().replaceFirst("https://", "wss://").replaceFirst("http://", "ws://")
        frameCounter.set(0); frame = null; streamInfo = null
        cursorX = -1f; cursorY = -1f; cursorFromServer = false; localCursorUntilNs = 0L
        screenOpen = true
        screenSocket = wsClient.newWebSocket(Request.Builder().url("$wsBase/ws/screen").build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                webSocket.send(JSONObject().put("token", token.trim()).toString())
            }
            override fun onMessage(webSocket: WebSocket, bytes: okio.ByteString) {
                if (gen != sessionGen) return
                val data = bytes.toByteArray()
                val decoded = BitmapFactory.decodeByteArray(data, 0, data.size)
                if (decoded != null) { frame = decoded; frameCounter.incrementAndGet() }
                webSocket.send("{\"type\":\"ack\"}")   // frame shown: the PC may send the next one (keeps the stream lag-free)
            }
            override fun onMessage(webSocket: WebSocket, text: String) {
                if (gen != sessionGen) return
                try {
                    val o = JSONObject(text)
                    when (o.optString("type")) {
                        "ready" -> webSocket.send(quality.configMessage())
                        "screen" -> streamInfo = StreamInfo(o.optInt("width"), o.optInt("height"), o.optInt("fps", 0))
                        "error" -> notice = Notice("Screen stream error: ${o.optString("message")}", true)
                    }
                } catch (_: Exception) { }
            }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(1000, null)
                if (gen != sessionGen) return
                notice = Notice("Screen stream closed" + if (reason.isNotBlank()) ": $reason" else ".", true)
                stopScreen()
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                if (gen != sessionGen) return
                notice = Notice("Screen stream disconnected: ${t.message ?: "network error"}", true)
                stopScreen()
            }
        })
        inputSocket = wsClient.newWebSocket(Request.Builder().url("$wsBase/ws/input").build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                webSocket.send(JSONObject().put("token", token.trim()).toString())
            }
            override fun onMessage(webSocket: WebSocket, text: String) {
                if (gen != sessionGen) return
                try {
                    val o = JSONObject(text)
                    when (o.optString("type")) {
                        "ready" -> webSocket.send("{\"type\":\"watch_cursor\",\"on\":true}")
                        "cursor" -> onServerCursor(o)
                    }
                } catch (_: Exception) { }
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                if (gen != sessionGen) return
                notice = Notice("Input connection failed: ${t.message ?: "network error"}", true)
            }
        })
    }

    fun stopScreen() {
        sessionGen++
        screenSocket?.close(1000, "User closed screen")
        inputSocket?.close(1000, "User closed screen")
        screenSocket = null; inputSocket = null
        screenOpen = false; frame = null; streamInfo = null
        cursorX = -1f; cursorY = -1f; cursorFromServer = false
    }

    fun sendInput(o: JSONObject) {
        inputSocket?.send(o.toString())
        predictCursor(o)
    }

    private fun onServerCursor(o: JSONObject) {
        pcWidth = o.optInt("w", pcWidth); pcHeight = o.optInt("h", pcHeight)
        cursorFromServer = true
        // While the finger is moving the pointer is already drawn where it will be; the PC's older answer would drag it back.
        if (System.nanoTime() < localCursorUntilNs) return
        cursorX = o.optDouble("nx", 0.0).toFloat(); cursorY = o.optDouble("ny", 0.0).toFloat()
    }

    /** Moves the drawn pointer right away with the same movement the PC is about to apply. */
    private fun predictCursor(o: JSONObject) {
        if (!cursorFromServer) return
        when (o.optString("type")) {
            "rel" -> if (pcWidth > 0 && pcHeight > 0 && cursorX >= 0f) {
                cursorX = (cursorX + o.optInt("dx") / pcWidth.toFloat()).coerceIn(0f, 1f)
                cursorY = (cursorY + o.optInt("dy") / pcHeight.toFloat()).coerceIn(0f, 1f)
                localCursorUntilNs = System.nanoTime() + LOCAL_CURSOR_NS
            }
            "move", "click", "down", "up" -> if (o.has("nx") && o.has("ny")) {
                cursorX = o.optDouble("nx").toFloat(); cursorY = o.optDouble("ny").toFloat()
                localCursorUntilNs = System.nanoTime() + LOCAL_CURSOR_NS
            }
        }
    }

    /** Called when the activity goes away: drop the sockets without touching UI state. */
    fun shutdown() {
        sessionGen++
        screenSocket?.cancel(); inputSocket?.cancel()
    }
}
