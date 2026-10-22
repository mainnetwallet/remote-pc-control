package com.mainnetwallet.remotepccontrol

import kotlin.math.hypot
import kotlin.math.max

/** What the trackpad asks the PC to do. All actions are relative to the current pointer position. */
interface PadSink {
    fun moveBy(dx: Int, dy: Int)
    fun button(name: String, down: Boolean)
    fun click(name: String)
    /** Wheel steps; > 0 scrolls up (same convention as the server's "scroll" message). */
    fun scroll(steps: Int)
}

/**
 * Laptop-trackpad gesture logic, free of Android/Compose types so it can be unit-tested on the JVM.
 * The UI feeds it one gesture at a time: [begin], any number of [update]s (and [tick]s when
 * [holdTimeoutMs] says so), then [end]. [cancel] must be safe to call at any time.
 *
 *  - one finger slide            -> [PadSink.moveBy] (scaled by [sensitivity], throttled to ~60/s)
 *  - one finger tap              -> left click
 *  - second tap shortly after    -> another left click (Windows turns the pair into a double click)
 *  - tap, then touch and slide   -> drag: left button down, moves, up on release/cancel
 *  - two finger tap              -> right click
 *  - two finger slide            -> scroll
 * All times are milliseconds from any monotonic clock (the touch event's uptime).
 */
class TrackpadEngine(private val sink: PadSink) {
    var sensitivity = 2f
    var slopPx = 8f
    var scrollStepPx = 40f

    companion object {
        const val TAP_MAX_MS = 180L          // one-finger tap: down->up at most this long
        const val TWO_FINGER_TAP_MAX_MS = 280L // fingers rarely land together
        const val DOUBLE_TAP_MS = 220L       // next touch within this after a tap = second tap / drag
        const val MOVE_INTERVAL_MS = 16L     // ~60 move messages per second
        const val MAX_REL = 500              // server clamps to this per message as well
        private const val NEVER = Long.MIN_VALUE / 4
    }

    private var lastTapUpMs = NEVER
    private var active = false
    private var startMs = 0L
    private var maxPointers = 0
    private var armed = false        // this touch began right after a tap: a slide/hold means drag
    private var moved = false
    private var dragging = false
    private var travelX = 0f
    private var travelY = 0f
    private var pendX = 0f
    private var pendY = 0f
    private var scrollAcc = 0f
    private var lastMoveMs = NEVER

    val isDragging: Boolean get() = dragging

    fun begin(nowMs: Long) {
        cancel()
        active = true; startMs = nowMs; maxPointers = 1; moved = false; dragging = false
        travelX = 0f; travelY = 0f; pendX = 0f; pendY = 0f; scrollAcc = 0f; lastMoveMs = NEVER
        armed = nowMs - lastTapUpMs <= DOUBLE_TAP_MS
        lastTapUpMs = NEVER
    }

    /** [dx]/[dy] = average finger movement (px) since the previous call; [pointers] = fingers down now. */
    fun update(nowMs: Long, pointers: Int, dx: Float, dy: Float) {
        if (!active) return
        if (pointers > maxPointers) maxPointers = pointers
        if (!moved) {
            travelX += dx; travelY += dy
            if (hypot(travelX, travelY) <= slopPx) return
            moved = true
            apply(nowMs, travelX, travelY)   // replay what was held back by the slop
        } else apply(nowMs, dx, dy)
    }

    /** Milliseconds until [tick] should be called (a held second touch becomes a drag), or null. */
    fun holdTimeoutMs(nowMs: Long): Long? =
        if (active && armed && !dragging && !moved && maxPointers == 1) max(1L, startMs + TAP_MAX_MS + 1 - nowMs) else null

    fun tick(nowMs: Long) {
        if (active && armed && !dragging && !moved && maxPointers == 1 && nowMs - startMs > TAP_MAX_MS) startDrag()
    }

    /** All fingers lifted. */
    fun end(nowMs: Long) {
        if (!active) return
        active = false
        if (dragging) { flush(nowMs, force = true); dragging = false; sink.button("left", false); return }
        if (moved) { if (maxPointers == 1) flush(nowMs, force = true); return }
        val duration = nowMs - startMs
        when {
            maxPointers == 1 && duration <= TAP_MAX_MS -> {
                sink.click("left")
                if (!armed) lastTapUpMs = nowMs   // a completed double-tap does not chain into a third
            }
            maxPointers == 2 && duration <= TWO_FINGER_TAP_MAX_MS -> sink.click("right")
        }
    }

    /** Gesture interrupted (composable removed, system cancel...). Never leaves the button pressed. */
    fun cancel() {
        val wasDragging = dragging
        active = false; dragging = false; moved = false
        pendX = 0f; pendY = 0f
        if (wasDragging) sink.button("left", false)
    }

    private fun startDrag() { dragging = true; sink.button("left", true) }

    private fun apply(nowMs: Long, dx: Float, dy: Float) {
        if (!dragging && armed && maxPointers == 1) startDrag()
        if (dragging || maxPointers == 1) {
            pendX += dx * sensitivity; pendY += dy * sensitivity
            flush(nowMs, force = false)
        } else {
            // Content follows the fingers like on a phone: fingers down -> page scrolls up.
            scrollAcc += dy
            val steps = (scrollAcc / scrollStepPx).toInt()
            if (steps != 0) { sink.scroll(steps); scrollAcc -= steps * scrollStepPx }
        }
    }

    private fun flush(nowMs: Long, force: Boolean) {
        if (!force && nowMs - lastMoveMs < MOVE_INTERVAL_MS) return
        // A forced flush (gesture end) drains everything, in messages of at most MAX_REL per axis.
        do {
            val ix = pendX.toInt().coerceIn(-MAX_REL, MAX_REL)
            val iy = pendY.toInt().coerceIn(-MAX_REL, MAX_REL)
            if (ix == 0 && iy == 0) return
            sink.moveBy(ix, iy)
            pendX -= ix; pendY -= iy; lastMoveMs = nowMs
        } while (force)
    }
}
