package dev.turbodesktop.remote

import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyPermanentlyInvalidatedException
import android.security.keystore.KeyProperties
import android.security.keystore.UserNotAuthenticatedException
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * Keystore-backed EC P-256 key. Non-exportable by construction (the private key never leaves the Keystore).
 *  - plain key: used for ordinary signed requests (no prompt).
 *  - auth key: requires user authentication (BiometricPrompt, strong biometric or device credential) within the last
 *    30 s, so one fingerprint covers a burst of signatures. Used to open a session and to answer approvals.
 */
class KeystoreSigner(private val alias: String, private val authRequired: Boolean) : Signer {
    private val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    init {
        if (!ks.containsAlias(alias)) generate()
    }

    private fun generate() {
        val b = KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
        if (authRequired) {
            b.setUserAuthenticationRequired(true)
            if (Build.VERSION.SDK_INT >= 30) {
                b.setUserAuthenticationParameters(
                    AUTH_WINDOW_SECONDS,
                    KeyProperties.AUTH_BIOMETRIC_STRONG or KeyProperties.AUTH_DEVICE_CREDENTIAL
                )
            } else {
                @Suppress("DEPRECATION")
                b.setUserAuthenticationValidityDurationSeconds(AUTH_WINDOW_SECONDS)
            }
        }
        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").run {
            initialize(b.build())
            generateKeyPair()
        }
    }

    override val publicKeyB64: String
        get() = Protocol.b64(ks.getCertificate(alias).publicKey.encoded)

    override fun sign(message: ByteArray): String {
        val key = ks.getKey(alias, null) as PrivateKey
        val sig = Signature.getInstance("SHA256withECDSA")
        sig.initSign(key)          // throws UserNotAuthenticatedException when outside the auth window
        sig.update(message)
        return Protocol.b64(sig.sign())
    }

    fun deleteKey() = ks.deleteEntry(alias)

    companion object {
        const val AUTH_WINDOW_SECONDS = 30
        fun needsAuth(e: Throwable): Boolean =
            e is UserNotAuthenticatedException || e is KeyPermanentlyInvalidatedException ||
                e.cause is UserNotAuthenticatedException
    }
}
