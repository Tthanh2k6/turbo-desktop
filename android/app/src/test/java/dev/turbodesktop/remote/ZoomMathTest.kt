package dev.turbodesktop.remote

import androidx.compose.ui.geometry.Offset
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ZoomMathTest {
    // 1920x1080 PC frame in a 2400x1080 landscape phone: fitted 1920x1080 px, centred
    private val cw = 2400f
    private val ch = 1080f
    private val fw = 1920f
    private val fh = 1080f

    @Test fun fitKeepsAspect() {
        assertEquals(1920f to 1080f, ZoomMath.fit(1920, 1080, cw, ch))
        assertEquals(1200f to 675f, ZoomMath.fit(960, 540, 1200f, 2000f))
    }

    @Test fun notZoomedMeansFullFrameAtChosenQuality() {
        assertNull(ZoomMath.visibleRegion(Offset.Zero, 1f, fw, fh, cw, ch))
        assertEquals("/screen.jpg?w=960&q=60", ZoomMath.screenPath(ScreenQuality.ECO, null, 0))
        assertEquals("/screen.jpg?w=1920&q=80", ZoomMath.screenPath(ScreenQuality.MAX, null, 0))
        assertEquals(ScreenQuality.SHARP, ScreenQuality.of("sharp"))
        assertEquals(ScreenQuality.ECO, ScreenQuality.of(null))
    }

    @Test fun zoomedCentreAskForTheMiddle() {
        // 2x at the centre: the middle half of the frame each way is visible vertically; horizontally the scaled
        // image (3840) is wider than the phone (2400), so 2400/3840 of it is visible
        val r = ZoomMath.visibleRegion(Offset.Zero, 2f, fw, fh, cw, ch)!!
        assertArrayEquals(intArrayOf(187, 250, 625, 500), r)
        assertEquals(2400, ZoomMath.drawnWidth(r, 2f, fw))
        assertEquals("/screen.jpg?w=1920&q=75&rx=187&ry=250&rw=625&rh=500", ZoomMath.screenPath(ScreenQuality.ECO, r, 2400))
    }

    @Test fun panIsClampedToTheImage() {
        val o = ZoomMath.clamp(Offset(10_000f, -10_000f), 2f, fw, fh, cw, ch)
        assertEquals(Offset(720f, -540f), o)       // (3840-2400)/2, (2160-1080)/2
        val r = ZoomMath.visibleRegion(o, 2f, fw, fh, cw, ch)!!
        assertEquals(0, r[0])                       // panned fully right: left edge of the PC screen
        assertEquals(500, r[1])                     // panned fully up: bottom half
    }

    @Test fun pinchKeepsThePointUnderTheFingers() {
        val c = Offset(300f, 100f)
        val o = ZoomMath.zoomAround(Offset.Zero, 1f, 3f, c, Offset.Zero)
        // image point under c before: c; after: (c - o) / 3 must equal c
        assertEquals(c, (c - o) / 3f)
    }
}
