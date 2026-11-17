package dev.turbodesktop.remote

import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** RFC 6238 (SHA1, 6 digits, 30 s). The phone never holds the secret in normal use (the owner types the code from
 *  Google Authenticator); this is used to validate input shape and by unit tests against the RFC vectors. */
object Totp {
    const val PERIOD = 30L

    fun code(secret: ByteArray, step: Long): String {
        val mac = Mac.getInstance("HmacSHA1").apply { init(SecretKeySpec(secret, "HmacSHA1")) }
        val h = mac.doFinal(java.nio.ByteBuffer.allocate(8).putLong(step).array())
        val off = h[h.size - 1].toInt() and 0x0F
        val num = ((h[off].toInt() and 0x7F) shl 24 or ((h[off + 1].toInt() and 0xFF) shl 16) or
            ((h[off + 2].toInt() and 0xFF) shl 8) or (h[off + 3].toInt() and 0xFF)) % 1_000_000
        return "%06d".format(num)
    }

    fun looksValid(input: String) = input.length == 6 && input.all { it in '0'..'9' }
}
