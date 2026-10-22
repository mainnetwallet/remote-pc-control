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
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import kotlin.math.abs

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
        Text("Trackpad", color = Color(0xFF55607A), style = MaterialTheme.typography.bodySmall)
    }
}

