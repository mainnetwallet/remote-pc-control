package com.mainnetwallet.remotepccontrol

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.coerceIn
import androidx.compose.ui.unit.dp
import java.util.Locale

/** Power actions on the PC. Restart, shutdown and sleep ask for confirmation first; lock does not. */
enum class PowerAction(
    val path: String, val label: String, val needsConfirm: Boolean, val body: String,
    val confirmTitle: String, val confirmBody: String
) {
    LOCK("lock", "Lock", false, "{}", "", ""),
    SLEEP("sleep", "Sleep", true, "{}", "Put the PC to sleep?", "The PC goes to sleep and drops off the network, so you cannot reach it until it wakes up."),
    RESTART("restart", "Restart", true, "{\"confirm\":true}", "Restart the PC?", "The PC restarts now. Unsaved work on it is lost."),
    SHUTDOWN("shutdown", "Shutdown", true, "{\"confirm\":true}", "Shut down the PC?", "The PC shuts down and stays unreachable until someone turns it on again. Unsaved work on it is lost.")
}

@Composable
fun DashboardScreen(c: RemoteController, onPower: (PowerAction) -> Unit) {
    val status = c.status
    val cs = MaterialTheme.colorScheme
    // Navy-to-black backdrop; the scroll column sits on top of it and keeps the system-bar insets.
    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(DashColors.BgTop, DashColors.BgBottom)))) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).screenInsets().padding(horizontal = 16.dp, vertical = 12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Column(Modifier.widthIn(max = 560.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(22.dp)) {
                // Header: PC name, connection badge, uptime, log out
                DashHeader(
                    hostname = status?.hostname ?: "Windows PC",
                    reachable = c.reachable,
                    uptime = status?.let { "Up ${formatUptime(it.uptimeSeconds)}" } ?: "Reading PC status…",
                    onLogout = { c.disconnect() }
                )

                val liveNote = when {
                    status == null -> "Waiting for data"
                    !c.reachable -> "Last known values"
                    else -> "Live"
                }
                // Values go stale while the PC is unreachable, so the monitoring blocks dim.
                val dim = if (c.reachable) 1f else 0.55f

                // CPU / memory / disk
                DashSection("System", liveNote) {
                    BoxWithConstraints(Modifier.fillMaxWidth().alpha(dim)) {
                        val ring = ((maxWidth - 20.dp) / 3 - 24.dp).coerceIn(60.dp, 80.dp)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            DashGauge("CPU", status?.cpu, "Processor\nload", ring, Modifier.weight(1f))
                            DashGauge(
                                "Memory", status?.memory,
                                status?.let { "${gb(it.memUsed)}\nof ${gb(it.memTotal)}" } ?: "–", ring, Modifier.weight(1f)
                            )
                            DashGauge(
                                "Disk", status?.disk,
                                status?.let { "${gb(it.diskUsed)}\nof ${gb(it.diskTotal)}" } ?: "–", ring, Modifier.weight(1f)
                            )
                        }
                    }
                }

                // Network
                DashSection("Network", liveNote) {
                    Row(Modifier.fillMaxWidth().alpha(dim), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        DashRateTile("Download", status?.rxPerSec, Glyph.DOWN, DashColors.Blue, Modifier.weight(1f))
                        DashRateTile("Upload", status?.txPerSec, Glyph.UP, DashColors.Violet, Modifier.weight(1f))
                    }
                }

                // Power: Lock, Sleep / Restart, Shutdown. Same callback as before; the confirmation dialogs live in MainActivity.
                DashSection("Power") {
                    PowerAction.values().toList().chunked(2).forEach { pair ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            pair.forEach { action ->
                                DashPowerTile(
                                    label = action.label,
                                    caption = if (action.needsConfirm) "Asks first" else "Instant",
                                    glyph = action.glyph(),
                                    tint = action.tint(),
                                    destructive = action == PowerAction.SHUTDOWN,
                                    onClick = { onPower(action) },
                                    modifier = Modifier.weight(1f)
                                )
                            }
                        }
                    }
                }

                // PIN lock
                DashSection("Security") { LockCard(c) }

                // Live screen
                DashSection("Live screen") {
                    DashPanel(Modifier.fillMaxWidth()) {
                        Text(
                            "Touch, trackpad and keyboard control of the logged-in desktop.",
                            style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant
                        )
                        Spacer(Modifier.height(14.dp))
                        Text("Quality", style = MaterialTheme.typography.labelLarge, color = cs.onSurfaceVariant)
                        Spacer(Modifier.height(8.dp))
                        DashQualityGrid(c.quality, { c.setQuality(it) })
                        Spacer(Modifier.height(10.dp))
                        Text(c.quality.hint, style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant)
                        Spacer(Modifier.height(16.dp))
                        Button(
                            onClick = { c.startScreen() }, shape = RoundedCornerShape(16.dp),
                            modifier = Modifier.fillMaxWidth().height(54.dp)
                        ) {
                            DashIcon(Glyph.PLAY, LocalContentColor.current, iconSize = 18.dp)
                            Spacer(Modifier.width(8.dp))
                            Text("Start screen session", style = MaterialTheme.typography.titleSmall)
                        }
                    }
                }

                if (c.notice.text.isNotBlank()) DashNotice(c.notice.text, c.notice.isError)
                Spacer(Modifier.height(4.dp))
            }
        }
    }
}

private fun PowerAction.glyph(): Glyph = when (this) {
    PowerAction.LOCK -> Glyph.LOCK
    PowerAction.SLEEP -> Glyph.MOON
    PowerAction.RESTART -> Glyph.RESTART
    PowerAction.SHUTDOWN -> Glyph.POWER
}

/** Blue for the everyday actions, amber for restart, red for the destructive shutdown. */
private fun PowerAction.tint(): Color = when (this) {
    PowerAction.LOCK -> DashColors.Blue
    PowerAction.SLEEP -> DashColors.Violet
    PowerAction.RESTART -> Palette.Warn
    PowerAction.SHUTDOWN -> Palette.Bad
}

/**
 * Locks or unlocks the PC's always-on PIN screen (separate from the Windows "Lock" button above:
 * this one stays locked permanently -- through sleep, restart and shutdown -- until unlocked here
 * or with the PIN at the PC itself).
 */
@Composable
private fun LockCard(c: RemoteController) {
    var showPinDialog by remember { mutableStateOf(false) }
    val state = c.lockState
    val cs = MaterialTheme.colorScheme
    val badgeText: String
    val badgeColor: Color
    when {
        state == null -> { badgeText = "Checking…"; badgeColor = cs.onSurfaceVariant }
        state.locked -> { badgeText = "Locked"; badgeColor = Palette.Warn }
        state.pinSet -> { badgeText = "Unlocked"; badgeColor = Palette.Good }
        else -> { badgeText = "No PIN set"; badgeColor = cs.onSurfaceVariant }
    }

    DashPanel(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier.size(44.dp).clip(RoundedCornerShape(14.dp)).background(badgeColor.copy(alpha = 0.16f)),
                contentAlignment = Alignment.Center
            ) { DashIcon(Glyph.LOCK, badgeColor, iconSize = 24.dp) }
            Spacer(Modifier.width(12.dp))
            Text("PIN lock", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            DashStatusPill(badgeText, badgeColor, pulsing = false)
        }
        Spacer(Modifier.height(12.dp))
        Text(
            when {
                state == null -> "Loading…"
                state.locked -> "Locked. Stays locked through sleep, restart and shutdown."
                state.pinSet -> "Unlocked. Won't lock again until you lock it here."
                else -> "Set a PIN first to turn this on."
            },
            style = MaterialTheme.typography.bodySmall, color = cs.onSurfaceVariant
        )
        Spacer(Modifier.height(14.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (state?.locked == true) {
                Button(
                    onClick = { c.unlockPc() }, shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.weight(1f).height(48.dp)
                ) { Text("Unlock", maxLines = 1) }
            } else {
                FilledTonalButton(
                    onClick = { c.lockPc() }, shape = RoundedCornerShape(14.dp),
                    modifier = Modifier.weight(1f).height(48.dp),
                    enabled = state?.pinSet == true
                ) { Text("Lock now", maxLines = 1) }
            }
            OutlinedButton(
                onClick = { showPinDialog = true }, shape = RoundedCornerShape(14.dp),
                modifier = Modifier.weight(1f).height(48.dp)
            ) { Text(if (state?.pinSet == true) "Change PIN" else "Set PIN", maxLines = 1) }
        }
    }

    if (showPinDialog) SetPinDialog(onDismiss = { showPinDialog = false }, onSave = { pin, onResult -> c.setLockPin(pin, onResult) })
}

@Composable
private fun SetPinDialog(onDismiss: () -> Unit, onSave: (String, (Boolean, String) -> Unit) -> Unit) {
    var pin by remember { mutableStateOf("") }
    var error by remember { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }
    val valid = pin.length in 4..12 && pin.all { it.isDigit() }

    AlertDialog(
        onDismissRequest = { if (!saving) onDismiss() },
        title = { Text("Set unlock PIN") },
        text = {
            Column {
                Text(
                    "4-12 digits. Used to unlock at the PC itself.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(
                    value = pin, onValueChange = { if (it.length <= 12) { pin = it.filter(Char::isDigit); error = "" } },
                    label = { Text("PIN") }, singleLine = true, modifier = Modifier.fillMaxWidth()
                )
                if (error.isNotBlank()) Text(error, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
        },
        confirmButton = {
            TextButton(
                enabled = valid && !saving,
                onClick = {
                    saving = true
                    onSave(pin) { ok, message -> saving = false; if (ok) onDismiss() else error = message }
                }
            ) { Text(if (saving) "Saving…" else "Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss, enabled = !saving) { Text("Cancel") } }
    )
}

private fun gb(bytes: Long): String = String.format(Locale.US, "%.1f GB", bytes / (1024.0 * 1024.0 * 1024.0))
