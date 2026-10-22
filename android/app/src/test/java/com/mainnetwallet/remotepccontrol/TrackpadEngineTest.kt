package com.mainnetwallet.remotepccontrol

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.abs

private class Rec : PadSink {
    val log = mutableListOf<String>()
    var mx = 0; var my = 0; var moves = 0; var biggest = 0
    override fun moveBy(dx: Int, dy: Int) { mx += dx; my += dy; moves++; biggest = maxOf(biggest, abs(dx), abs(dy)); log += "move" }
    override fun button(name: String, down: Boolean) { log += "$name-${if (down) "down" else "up"}" }
    override fun click(name: String) { log += "click-$name" }
    override fun scroll(steps: Int) { log += "scroll$steps" }
    fun actions() = log.filter { it != "move" }
}

class TrackpadEngineTest {
    private fun engine(r: Rec) = TrackpadEngine(r).apply { sensitivity = 2f; slopPx = 8f; scrollStepPx = 40f }

    /** Finger(s) down at t0, optional movement, up at t1. */
    private fun tap(e: TrackpadEngine, t0: Long, dur: Long = 60) { e.begin(t0); e.end(t0 + dur) }

    @Test fun oneFingerTapIsLeftClick() {
        val r = Rec(); val e = engine(r); tap(e, 1000)
        assertEquals(listOf("click-left"), r.log)
    }

    @Test fun longPressWithoutMovementDoesNothing() {
        val r = Rec(); val e = engine(r); e.begin(0); e.end(600)
        assertTrue(r.log.isEmpty())
    }

    @Test fun jitterUnderSlopIsIgnored() {
        val r = Rec(); val e = engine(r); e.begin(0); e.update(10, 1, 3f, 2f); e.update(20, 1, -2f, 1f); e.end(500)
        assertTrue(r.log.isEmpty())
    }

    @Test fun slideMovesPointerScaledBySensitivity() {
        val r = Rec(); val e = engine(r); e.begin(0)
        var t = 0L
        repeat(10) { t += 16; e.update(t, 1, 5f, -2f) }
        e.end(t + 10)
        assertEquals(100, r.mx); assertEquals(-40, r.my)           // 50px*2, -20px*2, nothing lost
        assertEquals(listOf<String>(), r.actions())                // a slide never clicks
    }

    @Test fun movesAreThrottledToAbout60PerSecondAndNothingIsLost() {
        val r = Rec(); val e = engine(r); e.begin(0)
        var t = 0L
        repeat(125) { t += 8; e.update(t, 1, 4f, 0f) }             // 1 s of 125 Hz touch events
        e.end(t)
        assertTrue("moves=${r.moves}", r.moves in 50..64)
        assertEquals(125 * 4 * 2, r.mx)
    }

    @Test fun subPixelRemaindersCarryOver() {
        val r = Rec(); val e = engine(r); e.sensitivity = 0.5f; e.begin(0)
        var t = 0L
        repeat(40) { t += 16; e.update(t, 1, 3f, 0f) }
        e.end(t)
        assertTrue(abs(r.mx - 60) <= 1)
    }

    @Test fun hugeDeltaIsSplitIntoMessagesOfAtMost500AndNothingIsLost() {
        val r = Rec(); val e = engine(r); e.begin(0); e.update(16, 1, 1000f, 0f)   // 2000 px after sensitivity
        assertEquals(500, r.mx)
        e.end(60)
        assertEquals(2000, r.mx); assertEquals(500, r.biggest); assertEquals(4, r.moves)
    }

    @Test fun twoQuickTapsAreTwoLeftClicks() {
        val r = Rec(); val e = engine(r); tap(e, 1000); tap(e, 1150)
        assertEquals(listOf("click-left", "click-left"), r.log)
    }

    @Test fun thirdTapDoesNotChainIntoDrag() {
        val r = Rec(); val e = engine(r); tap(e, 1000); tap(e, 1150)
        e.begin(1300); assertNull(e.holdTimeoutMs(1300)); e.update(1316, 1, 30f, 0f); e.end(1400)
        assertFalse(r.log.contains("left-down"))
    }

    @Test fun slowSecondTouchIsPlainMoveNotDrag() {
        val r = Rec(); val e = engine(r); tap(e, 1000)
        e.begin(1500); e.update(1516, 1, 30f, 0f); e.end(1600)
        assertEquals(listOf("click-left"), r.actions()); assertTrue(r.mx > 0)
    }

    @Test fun tapThenSlideIsDownMovesUp() {
        val r = Rec(); val e = engine(r); tap(e, 1000)
        e.begin(1100)
        var t = 1100L
        repeat(10) { t += 16; e.update(t, 1, 10f, 0f) }
        assertTrue(e.isDragging)
        e.end(t + 5)
        assertEquals(listOf("click-left", "left-down", "left-up"), r.actions())
        assertEquals("left-down", r.actions()[1]); assertEquals("left-up", r.log.last())
        assertEquals(200, r.mx)
    }

    @Test fun tapThenHoldStartsDragAfterTimeout() {
        val r = Rec(); val e = engine(r); tap(e, 1000); e.begin(1100)
        val wait = e.holdTimeoutMs(1100)!!
        assertTrue(wait in 1..TrackpadEngine.TAP_MAX_MS + 1)
        e.tick(1100 + wait); assertTrue(e.isDragging)
        assertNull(e.holdTimeoutMs(1500))
        e.end(1800)
        assertEquals(listOf("click-left", "left-down", "left-up"), r.actions())
    }

    @Test fun cancelDuringDragReleasesButton() {
        val r = Rec(); val e = engine(r); tap(e, 1000); e.begin(1100); e.update(1116, 1, 30f, 0f)
        e.cancel(); e.cancel()
        assertEquals(1, r.log.count { it == "left-up" }); assertFalse(e.isDragging)
        e.end(2000)                                                   // late end after cancel is ignored
        assertEquals(1, r.log.count { it == "left-up" })
    }

    @Test fun beginWhileDraggingReleasesPreviousButton() {
        val r = Rec(); val e = engine(r); tap(e, 1000); e.begin(1100); e.update(1116, 1, 30f, 0f)
        e.begin(1200)
        assertEquals(1, r.log.count { it == "left-up" })
    }

    @Test fun cancelWithoutDragSendsNothing() {
        val r = Rec(); val e = engine(r); e.begin(0); e.update(16, 1, 30f, 0f); r.log.clear(); e.cancel()
        assertTrue(r.log.isEmpty())
    }

    @Test fun twoFingerTapIsRightClickOnly() {
        val r = Rec(); val e = engine(r); e.begin(0); e.update(20, 2, 0f, 0f); e.end(150)
        assertEquals(listOf("click-right"), r.log)
    }

    @Test fun rightClickDoesNotArmDrag() {
        val r = Rec(); val e = engine(r); e.begin(0); e.update(20, 2, 0f, 0f); e.end(150)
        e.begin(200); assertNull(e.holdTimeoutMs(200))
    }

    @Test fun twoFingerSlideScrollsAndNeverMovesPointer() {
        val r = Rec(); val e = engine(r); e.begin(0)
        var t = 0L
        repeat(10) { t += 16; e.update(t, 2, 0f, 10f) }               // 100px down, step 40px
        e.end(t + 5)
        assertEquals(0, r.moves); assertEquals(listOf("scroll1", "scroll1"), r.actions().filter { it.startsWith("scroll") }.take(2))
        assertEquals(2, r.log.count { it.startsWith("scroll") })      // 100px => 2 full steps (+20px carried)
        assertFalse(r.log.any { it.startsWith("click") })
    }

    @Test fun twoFingerSlideUpScrollsDown() {
        val r = Rec(); val e = engine(r); e.begin(0); e.update(16, 2, 0f, -90f); e.end(40)
        assertEquals(listOf("scroll-2"), r.log)
    }

    @Test fun liftingOneFingerAfterTwoFingerGestureNeverJumpsPointer() {
        val r = Rec(); val e = engine(r); e.begin(0); e.update(16, 2, 0f, 30f); e.update(32, 1, 20f, 20f); e.end(60)
        assertEquals(0, r.moves)
    }

    @Test fun secondFingerWhileDraggingKeepsDragging() {
        val r = Rec(); val e = engine(r); tap(e, 1000); e.begin(1100); e.update(1116, 1, 30f, 0f); e.update(1132, 2, 10f, 0f)
        assertTrue(e.isDragging); e.end(1200)
        assertEquals("left-up", r.log.last())
    }

    @Test fun longTwoFingerHoldDoesNothing() {
        val r = Rec(); val e = engine(r); e.begin(0); e.update(20, 2, 0f, 0f); e.end(900)
        assertTrue(r.log.isEmpty())
    }

    @Test fun threeFingerTapDoesNothing() {
        val r = Rec(); val e = engine(r); e.begin(0); e.update(10, 3, 0f, 0f); e.end(100)
        assertTrue(r.log.isEmpty())
    }
}
