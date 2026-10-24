package com.mainnetwallet.remotepccontrol

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * The per-device unlock key. The private key is generated inside the Android Keystore, is
 * invalidated if biometric enrollment changes (a new fingerprint added revokes it), and never
 * leaves the hardware-backed keystore - only its public key and signatures do.
 */
object UnlockKeyStore {
    private const val ALIAS = "remote_pc_unlock_key"

    /** Creates the key pair if it does not already exist. Returns the public key as base64 DER SPKI. */
    fun ensureKeyPair(): String {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (!ks.containsAlias(ALIAS)) {
            val gen = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore")
            gen.initialize(
                KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
                    .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
                    .setDigests(KeyProperties.DIGEST_SHA256)
                    .setUserAuthenticationRequired(true)
                    // Every signature needs a fresh biometric prompt (no grace window): each unlock is its own approval.
                    .setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG)
                    .setInvalidatedByBiometricEnrollment(true)
                    .build()
            )
            gen.generateKeyPair()
        }
        val pub = ks.getCertificate(ALIAS).publicKey
        return Base64.encodeToString(pub.encoded, Base64.NO_WRAP)
    }

    fun hasKeyPair(): Boolean = try {
        KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.containsAlias(ALIAS)
    } catch (_: Exception) { false }

    /** The private key, for use inside a BiometricPrompt.CryptoObject (signing happens only after the prompt succeeds). */
    fun privateKey(): PrivateKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return ks.getKey(ALIAS, null) as PrivateKey
    }

    fun signature(): Signature = Signature.getInstance("SHA256withECDSA")

    /** Drops the local key (e.g. after the user revokes the device on the PC, or logs out). The PC-side approval is separate. */
    fun forget() {
        try {
            val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
            if (ks.containsAlias(ALIAS)) ks.deleteEntry(ALIAS)
        } catch (_: Exception) { }
    }
}

/** Decodes a base64 SPKI the agent returns in an error so callers never need to touch java.security directly. */
fun decodeSpkiOrNull(b64: String): java.security.PublicKey? = try {
    val bytes = Base64.decode(b64, Base64.NO_WRAP)
    KeyFactory.getInstance("EC").generatePublic(java.security.spec.X509EncodedKeySpec(bytes))
} catch (_: Exception) { null }
