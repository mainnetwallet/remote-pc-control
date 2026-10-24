package com.mainnetwallet.remotepccontrol

import android.util.Base64
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import org.json.JSONObject
import java.security.Signature
import kotlin.coroutines.resume

/** Card shown on the dashboard for the optional, disabled-by-default Windows unlock feature. */
@Composable
fun UnlockCard(c: RemoteController) {
    val activity = LocalContext.current as? FragmentActivity
    val scope = rememberCoroutineScope()
    var showPasswordDialog by remember { mutableStateOf(false) }
    var showEnrollDialog by remember { mutableStateOf(false) }
    var outcome by remember { mutableStateOf<UnlockOutcome?>(null) }

    LaunchedEffect(c.connected) { if (c.connected) c.refreshUnlockStatus() }
    val status = c.unlockStatus

    AppCard(Modifier.fillMaxWidth()) {
        Text("Unlock Windows", style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(4.dp))
        Text(
            when {
                status == null -> "Checking availability…"
                !status.ready -> status.reason.ifBlank { "Not installed on this PC yet. See docs/UNLOCK.md." }
                else -> "Unlocks the PC's own signed-in desktop. Windows verifies every attempt."
            },
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        if (status?.ready == true) {
            Spacer(Modifier.height(12.dp))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                FilledTonalButton(
                    onClick = { showPasswordDialog = true }, enabled = status.passwordAvailable && !c.unlockBusy,
                    modifier = Modifier.weight(1f).height(48.dp)
                ) { Text("PIN / Password") }
                FilledTonalButton(
                    onClick = {
                        if (activity == null) return@FilledTonalButton
                        scope.launch {
                            outcome = performBiometricUnlock(activity, c)
                        }
                    },
                    enabled = status.biometricAvailable && !c.unlockBusy && activity != null,
                    modifier = Modifier.weight(1f).height(48.dp)
                ) { Text("Fingerprint") }
            }
            Spacer(Modifier.height(10.dp))
            TextButton(onClick = { showEnrollDialog = true }, enabled = !c.unlockBusy) {
                Text(if (UnlockKeyStore.hasKeyPair()) "Re-enroll this phone" else "Enroll this phone for fingerprint unlock")
            }
            if (status.approvedDevices == 0 && UnlockKeyStore.hasKeyPair())
                Text(
                    "Waiting for approval on the PC (python -m app.unlock_admin approve …).",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            if (c.unlockBusy) { Spacer(Modifier.height(8.dp)); CircularProgressIndicator(Modifier.height(20.dp)) }
        }
        c.pendingEnrollment?.let { p ->
            Spacer(Modifier.height(8.dp))
            Text(
                "Device fingerprint: ${p.fingerprint}\nApprove it on the PC to finish enrollment.",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary
            )
        }
        outcome?.let { o ->
            Spacer(Modifier.height(8.dp))
            Text(o.message, style = MaterialTheme.typography.bodySmall, color = if (o.success) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)
        }
    }

    if (showEnrollDialog) EnrollDialog(c, onDismiss = { showEnrollDialog = false })
    if (showPasswordDialog) PasswordUnlockDialog(c, onDismiss = { showPasswordDialog = false }, onOutcome = { outcome = it })
}

@Composable
private fun EnrollDialog(c: RemoteController, onDismiss: () -> Unit) {
    var name by remember { mutableStateOf(android.os.Build.MODEL ?: "Android device") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Enroll this phone") },
        text = {
            Column {
                Text("Creates a device key protected by this phone's fingerprint. You'll still need to approve it once on the PC itself.")
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(value = name, onValueChange = { name = it.take(40) }, label = { Text("Device name") }, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            TextButton(onClick = {
                onDismiss()
                c.enrollThisDevice(name.ifBlank { "Android device" }) { }
            }) { Text("Enroll") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } }
    )
}

@Composable
private fun PasswordUnlockDialog(c: RemoteController, onDismiss: () -> Unit, onOutcome: (UnlockOutcome) -> Unit) {
    var credential by remember { mutableStateOf("") }
    var submitting by remember { mutableStateOf(false) }
    AlertDialog(
        onDismissRequest = { if (!submitting) onDismiss() },
        title = { Text("Unlock with Windows PIN/Password") },
        text = {
            Column {
                Text("Sent directly to the PC over the encrypted connection. Never saved on this phone.", style = MaterialTheme.typography.bodySmall)
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = credential, onValueChange = { if (it.length <= 128) credential = it },
                    label = { Text("PIN or password") }, singleLine = true, enabled = !submitting,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    modifier = Modifier.fillMaxWidth()
                )
                if (submitting) { Spacer(Modifier.height(10.dp)); CircularProgressIndicator(Modifier.height(18.dp)) }
            }
        },
        confirmButton = {
            TextButton(enabled = credential.isNotEmpty() && !submitting, onClick = {
                submitting = true
                c.unlockWithPassword(credential) { outcome ->
                    submitting = false
                    credential = ""   // cleared from the composable's state as soon as the request is sent
                    onOutcome(outcome)
                    if (outcome.success) onDismiss()
                }
            }) { Text("Unlock") }
        },
        dismissButton = { TextButton(enabled = !submitting, onClick = onDismiss) { Text("Cancel") } }
    )
}

/**
 * Full biometric unlock flow: fetch a fresh challenge -> prompt the fingerprint (which is required to even use the
 * signing key) -> sign it -> ask for the Windows credential to go with it -> submit both together. Returns only
 * once the PC (i.e. Windows) has answered, or the flow was cancelled/failed before that.
 */
private suspend fun performBiometricUnlock(activity: FragmentActivity, c: RemoteController): UnlockOutcome {
    if (!UnlockKeyStore.hasKeyPair()) return UnlockOutcome(false, "Enroll this phone first.")
    val manager = BiometricManager.from(activity)
    if (manager.canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG) != BiometricManager.BIOMETRIC_SUCCESS)
        return UnlockOutcome(false, "No usable fingerprint/biometric is set up on this phone.")

    val challenge = suspendCancellableCoroutine<Pair<JSONObject?, String?>> { cont ->
        val deviceId = c.thisDeviceId
        if (deviceId != null) {
            c.requestUnlockChallenge(deviceId) { ok, ch, err -> cont.resume(if (ok) ch to null else null to err) }
        } else {
            cont.resume(null to "Enroll this phone and have it approved on the PC first.")
        }
    }
    val (ch, err) = challenge
    if (ch == null) return UnlockOutcome(false, err ?: "Could not start a challenge.")

    val signatureBytes = signWithBiometricPrompt(activity, ch) ?: return UnlockOutcome(false, "Fingerprint approval was cancelled or failed.")
    val credential = askCredentialInline(activity) ?: return UnlockOutcome(false, "Cancelled.")

    return suspendCancellableCoroutine { cont ->
        c.unlockWithBiometric(ch.optString("device_id"), ch.optString("challenge_id"), Base64.encodeToString(signatureBytes, Base64.NO_WRAP), credential) {
            cont.resume(it)
        }
    }
}

/** Shows the system BiometricPrompt and signs the exact challenge bytes only after a successful scan. */
private suspend fun signWithBiometricPrompt(activity: FragmentActivity, challenge: JSONObject): ByteArray? = suspendCancellableCoroutine { cont ->
    val message = unlockSignedMessage(challenge)
    val sig = UnlockKeyStore.signature()
    sig.initSign(UnlockKeyStore.privateKey())
    val crypto = BiometricPrompt.CryptoObject(sig)
    val executor = ContextCompat.getMainExecutor(activity)
    val prompt = BiometricPrompt(activity, executor, object : BiometricPrompt.AuthenticationCallback() {
        override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
            val s = result.cryptoObject?.signature
            val bytes = try { s?.update(message); s?.sign() } catch (_: Exception) { null }
            if (cont.isActive) cont.resume(bytes)
        }
        override fun onAuthenticationError(code: Int, msg: CharSequence) { if (cont.isActive) cont.resume(null) }
        override fun onAuthenticationFailed() { /* a failed single scan; the prompt stays open for a retry */ }
    })
    prompt.authenticate(
        BiometricPrompt.PromptInfo.Builder()
            .setTitle("Unlock Windows")
            .setSubtitle("Confirm with your fingerprint")
            .setNegativeButtonText("Cancel")
            .build(),
        crypto
    )
    cont.invokeOnCancellation { prompt.cancelAuthentication() }
}

/** Exact byte layout the backend verifies against (see app/unlock.py:signed_message) - must match field-for-field. */
private fun unlockSignedMessage(ch: JSONObject): ByteArray {
    val parts = listOf(
        "RPC-UNLOCK-V1", ch.optString("op"), ch.optString("pc_id"), ch.optString("account"),
        ch.optInt("session").toString(), ch.optString("device_id"), ch.optString("challenge_id"),
        ch.optString("nonce"), ch.optLong("expires_at").toString()
    )
    return parts.joinToString("\n").toByteArray(Charsets.UTF_8)
}

/** A tiny blocking-style credential prompt shown right after the fingerprint succeeds, so both factors are given in one flow. */
private suspend fun askCredentialInline(activity: FragmentActivity): String? = suspendCancellableCoroutine { cont ->
    // Implemented as a system AlertDialog (not Compose) so it can be shown from this non-Composable suspend function.
    val input = android.widget.EditText(activity).apply {
        inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_PASSWORD
        hint = "Windows PIN or password"
    }
    val dialog = android.app.AlertDialog.Builder(activity)
        .setTitle("Confirm Windows PIN/Password")
        .setMessage("Fingerprint confirmed. Enter the PIN/password to complete the unlock.")
        .setView(input)
        .setCancelable(true)
        .setPositiveButton("Unlock") { _, _ -> if (cont.isActive) cont.resume(input.text?.toString()?.take(128)) }
        .setNegativeButton("Cancel") { _, _ -> if (cont.isActive) cont.resume(null) }
        .setOnCancelListener { if (cont.isActive) cont.resume(null) }
        .create()
    dialog.show()
    cont.invokeOnCancellation { dialog.dismiss() }
}
