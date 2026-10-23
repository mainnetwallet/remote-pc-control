package com.mainnetwallet.remotepccontrol

import android.content.Context
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import org.webrtc.DataChannel
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.MediaStreamTrack
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RTCStats
import org.webrtc.RtpReceiver
import org.webrtc.RtpTransceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.VideoTrack
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import java.util.Timer
import java.util.TimerTask

/** Process-wide WebRTC objects: the EGL context is shared by the hardware decoder and the video renderer. */
object RtcEngine {
    private var factory: PeerConnectionFactory? = null
    val egl: EglBase by lazy { EglBase.create() }

    @Synchronized
    fun factory(context: Context): PeerConnectionFactory {
        factory?.let { return it }
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context.applicationContext).createInitializationOptions()
        )
        val f = PeerConnectionFactory.builder()
            .setVideoDecoderFactory(DefaultVideoDecoderFactory(egl.eglBaseContext))
            .setVideoEncoderFactory(DefaultVideoEncoderFactory(egl.eglBaseContext, true, true))
            .createPeerConnectionFactory()
        factory = f
        return f
    }
}

/** What the WebRTC session reports back to the controller. All callbacks may arrive on any thread. */
interface RtcListener {
    fun onVideo(track: VideoTrack)
    fun onConnected()
    /** WebRTC cannot be used (or broke): the controller falls back to the WebSocket stream. */
    fun onFailed(reason: String)
    fun onScreen(width: Int, height: Int, fps: Int)
    fun onCursor(o: JSONObject)
    /** [decoded] counts the video frames decoded so far: above 0 means the picture really arrives. */
    fun onStats(rttMs: Int, fps: Int, kbps: Int, decodeMs: Int, decoded: Long)
}

// A phone's radio often drops the path for a moment ("disconnected") and ICE recovers by itself; only a longer outage ends WebRTC.
private const val DISCONNECT_GRACE_MS = 5000L

private open class SdpAdapter : SdpObserver {
    override fun onCreateSuccess(sdp: SessionDescription?) {}
    override fun onSetSuccess() {}
    override fun onCreateFailure(error: String?) {}
    override fun onSetFailure(error: String?) {}
}

/**
 * One WebRTC session to the PC (backend/app/webrtc.py, endpoint /ws/rtc).
 * Signaling goes over an authenticated WebSocket; video arrives as a receive-only track and input goes out on two data
 * channels: "input" (unordered, no retransmits: pointer moves) and "control" (reliable: everything else).
 */
class RtcClient(
    private val context: Context,
    private val client: OkHttpClient,
    private val wsBase: String,
    private val token: String,
    private val listener: RtcListener,
) {
    @Volatile private var closed = false
    @Volatile private var failedReported = false
    @Volatile private var connected = false
    private var signaling: WebSocket? = null
    private var pc: PeerConnection? = null
    private var inputChannel: DataChannel? = null
    private var controlChannel: DataChannel? = null
    private var statsTimer: Timer? = null
    private var disconnectTimer: Timer? = null
    private var lastBytes = 0L
    private var lastBytesAt = 0L
    @Volatile private var pingRttMs = -1
    private var pendingConfig: String? = null

    /** True when input can go out on the data channels (otherwise the caller uses the old input socket). */
    val controlOpen: Boolean get() = controlChannel?.state() == DataChannel.State.OPEN

    fun start(initialConfig: String) {
        pendingConfig = initialConfig
        signaling = client.newWebSocket(Request.Builder().url("$wsBase/ws/rtc").build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                webSocket.send(JSONObject().put("token", token).toString())
            }
            override fun onMessage(webSocket: WebSocket, text: String) {
                if (closed) return
                try { handleSignal(JSONObject(text)) } catch (e: Exception) { fail("signaling error: ${e.message}") }
            }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(1000, null) }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                // After the connection is up the signaling socket is not needed any more.
                if (!connected) fail("signaling failed: ${t.message ?: "network error"}")
            }
        })
    }

    private fun fail(reason: String) {
        if (closed || failedReported) return
        failedReported = true
        listener.onFailed(reason)
    }

    /** "Disconnected" is often a short radio hiccup: give ICE a few seconds to recover before giving up on WebRTC. */
    @Synchronized
    private fun startDisconnectTimer() {
        if (closed) return
        disconnectTimer?.cancel()
        val timer = Timer("rtc-disconnect", true)
        disconnectTimer = timer
        timer.schedule(object : TimerTask() {
            override fun run() { fail("the connection to the PC was lost") }
        }, DISCONNECT_GRACE_MS)
    }

    @Synchronized
    private fun cancelDisconnectTimer() {
        disconnectTimer?.cancel()
        disconnectTimer = null
    }

    private fun handleSignal(o: JSONObject) {
        when (o.optString("type")) {
            "ready" -> createPeer(o.optJSONArray("ice_servers"))
            "answer" -> {
                val sdp = SessionDescription(SessionDescription.Type.ANSWER, o.getString("sdp"))
                pc?.setRemoteDescription(object : SdpAdapter() {
                    override fun onSetFailure(error: String?) { fail("answer rejected: $error") }
                }, sdp)
            }
            "candidate" -> {
                val c = o.optJSONObject("candidate") ?: return   // null = the PC has no more candidates
                val cand = c.optString("candidate")
                if (cand.isNotEmpty()) pc?.addIceCandidate(IceCandidate(c.optString("sdpMid").ifEmpty { "0" }, c.optInt("sdpMLineIndex", 0), cand))
            }
            "state" -> if (o.optString("state") == "failed") fail("the PC reports a failed connection")
            "unavailable" -> fail(o.optString("reason", "WebRTC unavailable"))
            "error" -> fail(o.optString("message", "WebRTC error"))
        }
    }

    private fun iceServers(arr: JSONArray?): List<PeerConnection.IceServer> {
        val out = ArrayList<PeerConnection.IceServer>()
        if (arr == null) return out
        for (i in 0 until arr.length()) {
            val s = arr.optJSONObject(i) ?: continue
            val urls = ArrayList<String>()
            when (val u = s.opt("urls")) {
                is String -> urls.add(u)
                is JSONArray -> for (k in 0 until u.length()) urls.add(u.optString(k))
            }
            if (urls.isEmpty()) continue
            val b = PeerConnection.IceServer.builder(urls)
            if (s.has("username")) b.setUsername(s.optString("username"))
            if (s.has("credential")) b.setPassword(s.optString("credential"))
            out.add(b.createIceServer())
        }
        return out
    }

    private fun createPeer(servers: JSONArray?) {
        val factory = RtcEngine.factory(context)
        val config = PeerConnection.RTCConfiguration(iceServers(servers)).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
        }
        val peer = factory.createPeerConnection(config, object : PeerConnection.Observer {
            override fun onSignalingChange(state: PeerConnection.SignalingState?) {}
            override fun onIceConnectionChange(state: PeerConnection.IceConnectionState?) {}
            override fun onIceConnectionReceivingChange(receiving: Boolean) {}
            override fun onIceGatheringChange(state: PeerConnection.IceGatheringState?) {
                if (state == PeerConnection.IceGatheringState.COMPLETE) {
                    signaling?.send(JSONObject().put("type", "candidate").put("candidate", JSONObject.NULL).toString())
                }
            }
            override fun onIceCandidate(c: IceCandidate?) {
                if (c == null || closed) return
                val cand = JSONObject().put("candidate", c.sdp).put("sdpMid", c.sdpMid).put("sdpMLineIndex", c.sdpMLineIndex)
                signaling?.send(JSONObject().put("type", "candidate").put("candidate", cand).toString())
            }
            override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>?) {}
            override fun onAddStream(stream: MediaStream?) {}
            override fun onRemoveStream(stream: MediaStream?) {}
            override fun onDataChannel(channel: DataChannel?) {}
            override fun onRenegotiationNeeded() {}
            override fun onAddTrack(receiver: RtpReceiver?, streams: Array<out MediaStream>?) {}
            override fun onTrack(transceiver: RtpTransceiver?) {
                val track = transceiver?.receiver?.track()
                if (track is VideoTrack) listener.onVideo(track)
            }
            override fun onConnectionChange(state: PeerConnection.PeerConnectionState?) {
                when (state) {
                    PeerConnection.PeerConnectionState.CONNECTED -> {
                        cancelDisconnectTimer()   // it came back by itself
                        if (!connected) { connected = true; listener.onConnected(); startStats() }
                    }
                    PeerConnection.PeerConnectionState.FAILED -> { cancelDisconnectTimer(); fail("the connection to the PC failed") }
                    PeerConnection.PeerConnectionState.DISCONNECTED -> if (connected) startDisconnectTimer()
                    else -> {}
                }
            }
        }) ?: run { fail("could not create the peer connection"); return }
        pc = peer

        val transceiver = peer.addTransceiver(
            MediaStreamTrack.MediaType.MEDIA_TYPE_VIDEO,
            RtpTransceiver.RtpTransceiverInit(RtpTransceiver.RtpTransceiverDirection.RECV_ONLY)
        )
        // H.264 first: the PC encodes H.264 with a low-latency (hardware) encoder, and the phone decodes it in hardware.
        try {
            val codecs = factory.getRtpReceiverCapabilities(MediaStreamTrack.MediaType.MEDIA_TYPE_VIDEO).codecs
            val h264 = codecs.filter { it.name.equals("H264", ignoreCase = true) }
            if (h264.isNotEmpty()) transceiver.setCodecPreferences(h264 + codecs.filterNot { it in h264 })
        } catch (_: Exception) { /* keep the default order */ }

        inputChannel = peer.createDataChannel("input", DataChannel.Init().apply { ordered = false; maxRetransmits = 0 })
            .also { it.registerObserver(ChannelObserver(it)) }
        controlChannel = peer.createDataChannel("control", DataChannel.Init())
            .also { it.registerObserver(ChannelObserver(it)) }

        peer.createOffer(object : SdpAdapter() {
            override fun onCreateSuccess(sdp: SessionDescription?) {
                if (sdp == null || closed) return
                peer.setLocalDescription(object : SdpAdapter() {
                    override fun onSetSuccess() {
                        signaling?.send(JSONObject().put("type", "offer").put("sdp", sdp.description).toString())
                    }
                    override fun onSetFailure(error: String?) { fail("local description failed: $error") }
                }, sdp)
            }
            override fun onCreateFailure(error: String?) { fail("offer failed: $error") }
        }, MediaConstraints())
    }

    private inner class ChannelObserver(private val channel: DataChannel) : DataChannel.Observer {
        override fun onBufferedAmountChange(previousAmount: Long) {}
        override fun onStateChange() {
            if (channel.label() == "control" && channel.state() == DataChannel.State.OPEN) {
                pendingConfig?.let { sendControl(it) }
                sendControl("{\"type\":\"watch_cursor\",\"on\":true}")
            }
        }
        override fun onMessage(buffer: DataChannel.Buffer?) {
            if (buffer == null || buffer.binary) return
            val bytes = ByteArray(buffer.data.remaining()).also { buffer.data.get(it) }
            try {
                val o = JSONObject(String(bytes, StandardCharsets.UTF_8))
                when (o.optString("type")) {
                    "screen" -> listener.onScreen(o.optInt("width"), o.optInt("height"), o.optInt("fps", 0))
                    "cursor" -> listener.onCursor(o)
                    "pong" -> pingRttMs = ((System.nanoTime() / 1_000_000L) - o.optLong("t")).toInt().coerceAtLeast(0)
                }
            } catch (_: Exception) { }
        }
    }

    private fun send(channel: DataChannel?, text: String): Boolean {
        if (channel == null || channel.state() != DataChannel.State.OPEN) return false
        return channel.send(DataChannel.Buffer(ByteBuffer.wrap(text.toByteArray(StandardCharsets.UTF_8)), false))
    }

    /** Reliable and ordered: clicks, keys, scroll, config. */
    fun sendControl(text: String): Boolean = send(controlChannel, text)

    /** Sends one input message; pointer moves take the unreliable channel, everything else the reliable one. */
    fun sendInput(o: JSONObject): Boolean {
        val text = o.toString()
        val type = o.optString("type")
        return if (type == "move" || type == "rel") (send(inputChannel, text) || send(controlChannel, text))
        else send(controlChannel, text)
    }

    private fun startStats() {
        val timer = Timer("rtc-stats", true)
        statsTimer = timer
        timer.schedule(object : TimerTask() {
            override fun run() {
                if (closed) return
                sendControl("{\"type\":\"ping\",\"t\":${System.nanoTime() / 1_000_000L}}")
                pc?.getStats { report ->
                    var rtt = pingRttMs
                    var fps = 0
                    var kbps = 0
                    var decodeMs = 0
                    var decoded = 0L
                    for (s: RTCStats in report.statsMap.values) {
                        val m = s.members
                        when (s.type) {
                            "inbound-rtp" -> if (m["kind"] == "video") {
                                fps = (m["framesPerSecond"] as? Number)?.toInt() ?: fps
                                val bytes = (m["bytesReceived"] as? Number)?.toLong() ?: 0L
                                val now = System.nanoTime() / 1_000_000L
                                if (lastBytesAt > 0 && now > lastBytesAt && bytes >= lastBytes) kbps = ((bytes - lastBytes) * 8 / (now - lastBytesAt)).toInt()
                                lastBytes = bytes; lastBytesAt = now
                                val frames = (m["framesDecoded"] as? Number)?.toDouble() ?: 0.0
                                val total = (m["totalDecodeTime"] as? Number)?.toDouble() ?: 0.0
                                if (frames > 0) decodeMs = (total / frames * 1000).toInt()
                                decoded = frames.toLong()
                            }
                            "candidate-pair" -> if (m["nominated"] == true && m["state"] == "succeeded" && rtt < 0) {
                                rtt = ((m["currentRoundTripTime"] as? Number)?.toDouble() ?: 0.0).times(1000).toInt()
                            }
                        }
                    }
                    listener.onStats(rtt, fps, kbps, decodeMs, decoded)
                }
            }
        }, 1000L, 1000L)
    }

    fun close() {
        if (closed) return
        closed = true
        cancelDisconnectTimer()
        statsTimer?.cancel(); statsTimer = null
        try { signaling?.send("{\"type\":\"bye\"}") } catch (_: Exception) { }
        try { signaling?.close(1000, null) } catch (_: Exception) { }
        signaling = null
        try { inputChannel?.unregisterObserver(); inputChannel?.close(); inputChannel?.dispose() } catch (_: Exception) { }
        try { controlChannel?.unregisterObserver(); controlChannel?.close(); controlChannel?.dispose() } catch (_: Exception) { }
        inputChannel = null; controlChannel = null
        try { pc?.close(); pc?.dispose() } catch (_: Exception) { }
        pc = null
    }
}
