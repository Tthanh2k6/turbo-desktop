package dev.turbodesktop.remote

import androidx.compose.foundation.Image
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.IntOffset
import kotlinx.coroutines.delay

/** Screen-view quality presets: full-frame width and JPEG quality the hub is asked for. */
enum class ScreenQuality(val key: String, val width: Int, val jpegQ: Int) {
    ECO("eco", 960, 60), SHARP("sharp", 1600, 70), MAX("max", 1920, 80);

    companion object {
        fun of(key: String?) = entries.firstOrNull { it.key == key } ?: ECO
    }
}

/** A sharp crop of the zoomed part of the PC screen; region = x, y, w, h in thousandths of the full frame. */
class ScreenCrop(val bitmap: ImageBitmap, val region: IntArray)

object ZoomMath {
    const val MAX_SCALE = 8f
    const val ZOOMED = 1.05f
    const val MAX_CROP_WIDTH = 1920

    /** URL for the next frame: the zoomed region at the size it is drawn (never more than the PC's pixels, the
     *  hub does not upscale), or the full frame at the chosen quality. */
    fun screenPath(q: ScreenQuality, region: IntArray?, drawnWidthPx: Int): String =
        if (region == null) "/screen.jpg?w=${q.width}&q=${q.jpegQ}"
        else "/screen.jpg?w=${drawnWidthPx.coerceIn(320, MAX_CROP_WIDTH)}&q=75" +
            "&rx=${region[0]}&ry=${region[1]}&rw=${region[2]}&rh=${region[3]}"

    /** Size of an image of aspect [imgW]/[imgH] fitted (ContentScale.Fit) into the container. */
    fun fit(imgW: Int, imgH: Int, cw: Float, ch: Float): Pair<Float, Float> {
        if (imgW <= 0 || imgH <= 0 || cw <= 0f || ch <= 0f) return 0f to 0f
        val s = minOf(cw / imgW, ch / imgH)
        return imgW * s to imgH * s
    }

    /** Keeps the scaled image covering the container where it can (no empty band when zoomed in). */
    fun clamp(offset: Offset, scale: Float, fw: Float, fh: Float, cw: Float, ch: Float): Offset {
        val mx = ((fw * scale - cw) / 2f).coerceAtLeast(0f)
        val my = ((fh * scale - ch) / 2f).coerceAtLeast(0f)
        return Offset(offset.x.coerceIn(-mx, mx), offset.y.coerceIn(-my, my))
    }

    /** New offset after a pinch around [centroid] (relative to the container centre) plus a pan. */
    fun zoomAround(offset: Offset, scale: Float, newScale: Float, centroid: Offset, pan: Offset): Offset =
        centroid - (centroid - offset) * (newScale / scale) + pan

    /** Visible part of the image, in thousandths (x, y, w, h); null when the whole image is visible. */
    fun visibleRegion(offset: Offset, scale: Float, fw: Float, fh: Float, cw: Float, ch: Float): IntArray? {
        if (scale <= ZOOMED || fw <= 0f || fh <= 0f) return null
        val sw = fw * scale
        val sh = fh * scale
        val left = cw / 2f + offset.x - sw / 2f
        val top = ch / 2f + offset.y - sh / 2f
        val x0 = ((0f - left) / sw).coerceIn(0f, 1f)
        val x1 = ((cw - left) / sw).coerceIn(0f, 1f)
        val y0 = ((0f - top) / sh).coerceIn(0f, 1f)
        val y1 = ((ch - top) / sh).coerceIn(0f, 1f)
        if (x1 - x0 >= 0.999f && y1 - y0 >= 0.999f) return null
        val rx = (x0 * 1000).toInt()
        val ry = (y0 * 1000).toInt()
        return intArrayOf(rx, ry, ((x1 * 1000).toInt() - rx).coerceAtLeast(1), ((y1 * 1000).toInt() - ry).coerceAtLeast(1))
    }

    /** How many screen pixels the region is drawn across (what the crop should be fetched at). */
    fun drawnWidth(region: IntArray, scale: Float, fw: Float): Int = (region[2] / 1000f * fw * scale).toInt()
}

/**
 * The PC screen with pinch-to-zoom, drag to pan and double-tap (zoomed: back to normal; not zoomed: 2.5x there).
 * While zoomed, the hub is asked for just the visible part at the size it is drawn, so text stays sharp without
 * sending bigger full frames. The sharp crop is drawn inside the same transform, so it stays aligned while panning.
 */
@Composable
fun ZoomableScreen(bitmap: ImageBitmap, modifier: Modifier = Modifier, frameModifier: Modifier = Modifier) {
    val crop by Graph.screenCrop.collectAsState()
    BoxWithConstraints(modifier.fillMaxSize().testTag("zoomableScreen"), contentAlignment = Alignment.Center) {
        val density = LocalDensity.current
        val cw = constraints.maxWidth.toFloat()
        val ch = constraints.maxHeight.toFloat()
        val (fw, fh) = ZoomMath.fit(bitmap.width, bitmap.height, cw, ch)
        var scale by remember { mutableFloatStateOf(1f) }
        var offset by remember { mutableStateOf(Offset.Zero) }

        // Ask for a sharp crop shortly after the view settles; drop it when back to normal.
        LaunchedEffect(scale, offset, fw, fh) {
            val region = ZoomMath.visibleRegion(offset, scale, fw, fh, cw, ch)
            if (region == null) {
                Graph.setZoom(null, 0)
            } else {
                delay(250)
                Graph.setZoom(region, ZoomMath.drawnWidth(region, scale, fw))
                Graph.fetchScreenFrame()
            }
        }

        Box(
            Modifier
                .fillMaxSize()
                .pointerInput(fw, fh, cw, ch) {
                    detectTapGestures(onDoubleTap = { tap ->
                        if (scale > ZoomMath.ZOOMED) {
                            scale = 1f; offset = Offset.Zero
                        } else {
                            val s = 2.5f
                            val c = Offset(tap.x - cw / 2f, tap.y - ch / 2f)
                            offset = ZoomMath.clamp(ZoomMath.zoomAround(Offset.Zero, 1f, s, c, Offset.Zero), s, fw, fh, cw, ch)
                            scale = s
                        }
                    })
                }
                .pointerInput(fw, fh, cw, ch) {
                    detectTransformGestures { centroid, pan, zoom, _ ->
                        val ns = (scale * zoom).coerceIn(1f, ZoomMath.MAX_SCALE)
                        val c = Offset(centroid.x - cw / 2f, centroid.y - ch / 2f)
                        val raw = ZoomMath.zoomAround(offset, scale, ns, c, pan)
                        scale = ns
                        offset = if (ns <= 1f) Offset.Zero else ZoomMath.clamp(raw, ns, fw, fh, cw, ch)
                    }
                },
            contentAlignment = Alignment.Center,
        ) {
            Box(
                Modifier
                    .size(with(density) { fw.toDp() }, with(density) { fh.toDp() })
                    .graphicsLayer {
                        scaleX = scale; scaleY = scale
                        translationX = offset.x; translationY = offset.y
                    }
                    .then(frameModifier),
            ) {
                Image(bitmap = bitmap, contentDescription = null, contentScale = ContentScale.FillBounds,
                    modifier = Modifier.fillMaxSize())
                val cr = crop
                if (cr != null && scale > ZoomMath.ZOOMED) {
                    val r = cr.region
                    Image(
                        bitmap = cr.bitmap, contentDescription = null, contentScale = ContentScale.FillBounds,
                        modifier = Modifier
                            .offset { IntOffset((r[0] / 1000f * fw).toInt(), (r[1] / 1000f * fh).toInt()) }
                            .size(with(density) { (r[2] / 1000f * fw).toDp() }, with(density) { (r[3] / 1000f * fh).toDp() })
                            .testTag("zoomCrop"),
                    )
                }
            }
        }
    }
}
