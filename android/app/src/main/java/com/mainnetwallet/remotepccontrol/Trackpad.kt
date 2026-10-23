package com.mainnetwallet.remotepccontrol

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import kotlinx.coroutines.withTimeoutOrNull
import kotlin.math.abs

private const val TAP_TIMEOUT_MS = 300L          // finger down -> up shorter than this is a tap
private const val DOUBLE_TAP_WINDOW_MS = 300L    // a touch this soon after a tap is a double tap / tap-then-slide
private const val MOVE_INTERVAL_MS = 8L          // up to about 120 pointer updates per second (the PC merges bursts)
private const val START_MOVE_DP = 2f             // the pointer starts following the finger after this much travel (a tap may wobble)
private const val ACCEL_PER_DP_MS = 1.5f         // extra pointer gain per dp/ms of finger speed: slow = precise, fast flick = far
private const val ACCEL_MAX = 2.5f               // the extra gain never exceeds this (total gain 3.5x)
private const val MAX_REL_STEP = 500             // the server clamps "rel" to +-500 per message
private const val PAD_PC_PX_PER_DP = 2f          // PC pixels per dp of finger travel at speed 1.0

/**
 * Laptop-style trackpad (plain black surface, no picture of the PC).
 *  one finger slide = relative move, tap = left click, second tap soon after = double click,
 *  tap then slide = drag (left button held), two-finger tap = right click, two-finger slide = scroll.
 * Taps are sent as plain clicks at the current pointer; two quick taps become a double click on the PC.
 */
@Composable
fun Trackpad(sensitivity: Float, send: (JSONObject) -> Unit, modifier: Modifier = Modifier) {
    val sendNow by rememberUpdatedState(send)
    val speedNow by rememberUpdatedState(sensitivity)
    val shape = RoundedCornerShape(14.dp)
    Box(
        modifier.background(Color(0xFF06080C), shape).border(1.dp, Palette.Outline, shape)
            .pointerInput(Unit) {
                var lastTapUpMs = 0L   // survives between gestures (needed for double tap / tap-then-slide)
                val slop = viewConfiguration.touchSlop
                val scrollStepPx = 14.dp.toPx()
                val startMovePx = START_MOVE_DP.dp.toPx()
                awaitEachGesture {
                    val first = awaitFirstDown(requireUnconsumed = false)
                    val downMs = first.uptimeMillis
                    val tapDrag = lastTapUpMs != 0L && downMs - lastTapUpMs <= DOUBLE_TAP_WINDOW_MS
                    lastTapUpMs = 0L
                    var maxPointers = 1
                    var prevPressed = 1
                    var releaseMs = 0L
                    var moved = false        // one finger went past touch slop
                    var moveStarted = false  // one finger went past the (much smaller) distance after which the pointer follows it
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
                            val waiting = (moved || moveStarted) && (abs(pendingX) >= 1f || abs(pendingY) >= 1f)
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
                                val dtMs = (c.uptimeMillis - c.previousUptimeMillis).coerceAtLeast(1L)
                                val speedDpMs = d.getDistance() / density / dtMs
                                val gain = 1f + minOf(ACCEL_MAX, speedDpMs * ACCEL_PER_DP_MS)
                                val pxToPc = speedNow * PAD_PC_PX_PER_DP / density * gain
                                pendingX += d.x * pxToPc; pendingY += d.y * pxToPc
                                if (!moveStarted && (c.position - first.position).getDistance() > startMovePx) moveStarted = true
                                if (!moved && (c.position - first.position).getDistance() > slop) {
                                    moved = true
                                    if (tapDrag) { dragging = true; sendNow(JSONObject().put("type", "down").put("button", "left")) }
                                }
                                if (moved || moveStarted) flush(false)
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
                            else {
                                if (moveStarted) flush(true)
                                if (heldMs <= TAP_TIMEOUT_MS) {
                                    sendNow(JSONObject().put("type", "click").put("button", "left"))
                                    if (!tapDrag) lastTapUpMs = releaseMs
                                }
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
        Text("Trackpad", color = Color(0xFF55607A), style = MaterialTheme.typography.bodySmall)
    }
}

