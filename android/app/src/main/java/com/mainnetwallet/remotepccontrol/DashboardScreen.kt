package com.mainnetwallet.remotepccontrol

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardOptions
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.PasswordVisualTransformation
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DialogProperties
import androidx.compose.material3.FilledTonalButton
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
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
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .screenInsets()
            .padding(horizontal = DesignTokens.SpaceLG, vertical = DesignTokens.SpaceMD),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Column(
            Modifier.widthIn(max = 560.dp).fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceLG)
        ) {
            // ===== CONNECTION HEADER =====
            ConnectionHeader(c)

            // ===== SYSTEM RESOURCE CARDS =====
            SystemResourcesSection(c)

            // ===== NETWORK STATISTICS =====
            NetworkSection(c)

            // ===== POWER CONTROLS =====
            PowerControlsSection(c, onPower)

            // ===== PIN LOCK =====
            LockCard(c)

            // ===== LIVE SCREEN CONTROLS =====
            LiveScreenSection(c)

            // ===== NOTICES =====
            if (c.notice.text.isNotBlank()) {
                NoticeBanner(c.notice)
            }
            Spacer(Modifier.height(DesignTokens.SpaceMD))
        }
    }
}

/** Connection header with status, PC name, uptime, and logout */
@Composable
private fun ConnectionHeader(c: RemoteController) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(DesignTokens.SpaceSM)
            ) {
                PulsingStatusDot(
                    color = if (c.reachable) Palette.Success else Palette.Danger,
                    size = 10.dp,
                    enabled = c.reachable
                )
                Text(
                    if (c.reachable) "Connected" else "Offline, retrying…",
                    style = typo.labelLarge,
                    color = colors.onSurfaceVariant
                )
            }
            Spacer(Modifier.height(DesignTokens.SpaceXS))
            Text(
                status?.hostname ?: "Windows PC",
                style = typo.headlineSmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                color = colors.onSurface
            )
            status?.let {
                Text(
                    "Up ${formatUptime(it.uptimeSeconds)}",
                    style = typo.bodySmall,
                    color = colors.onSurfaceVariant
                )
            }
        }
        OutlineActionButton(
            text = "Log out",
            onClick = { c.disconnect() },
            modifier = Modifier.width(100.dp).height(DesignTokens.TouchTargetComfortable)
        )
    }
}

/** System resources: CPU, Memory, Disk with circular gauges */
@Composable
private fun SystemResourcesSection(c: RemoteController) {
    val status = c.status

    ElevatedCard(Modifier.fillMaxWidth(), padding = DesignTokens.SpaceLG) {
        Column(verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceLG)) {
            SectionHeader("System Resources")
            Spacer(Modifier.height(DesignTokens.SpaceXS))

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(DesignTokens.SpaceSM)
            ) {
                GaugeCard("CPU", status?.cpu, "Processor load", Modifier.weight(1f))
                GaugeCard(
                    "Memory",
                    status?.memory,
                    status?.let { "${formatBytes(it.memUsed)} / ${formatBytes(it.memTotal)}" } ?: "–",
                    Modifier.weight(1f)
                )
                GaugeCard(
                    "Disk",
                    status?.disk,
                    status?.let { "${formatBytes(it.diskUsed)} / ${formatBytes(it.diskTotal)}" } ?: "–",
                    Modifier.weight(1f)
                )
            }
        }
    }
}

/** Network statistics: Download and Upload speeds */
@Composable
private fun NetworkSection(c: RemoteController) {
    val status = c.status
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    AppCard(Modifier.fillMaxWidth(), padding = DesignTokens.SpaceLG) {
        Column(verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceLG)) {
            SectionHeader("Network")
            Spacer(Modifier.height(DesignTokens.SpaceXS))

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(DesignTokens.SpaceMD)
            ) {
                RateColumn(
                    "Download",
                    status?.rxPerSec,
                    Modifier.weight(1f).fillMaxWidth()
                )
                SubtleDivider(Modifier.height(48.dp).padding(vertical = DesignTokens.SpaceSM))
                RateColumn(
                    "Upload",
                    status?.txPerSec,
                    Modifier.weight(1f).fillMaxWidth()
                )
            }
        }
    }
}

/** Power controls: Lock, Sleep, Restart, Shutdown */
@Composable
private fun PowerControlsSection(c: RemoteController, onPower: (PowerAction) -> Unit) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    AppCard(Modifier.fillMaxWidth(), padding = DesignTokens.SpaceLG) {
        Column(verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceLG)) {
            SectionHeader("Power Controls")
            Spacer(Modifier.height(DesignTokens.SpaceXS))

            // Row 1: Lock, Sleep
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(DesignTokens.SpaceSM)
            ) {
                SecondaryActionButton(
                    text = "Lock",
                    onClick = { onPower(PowerAction.LOCK) },
                    modifier = Modifier.weight(1f)
                )
                SecondaryActionButton(
                    text = "Sleep",
                    onClick = { onPower(PowerAction.SLEEP) },
                    modifier = Modifier.weight(1f)
                )
            }

            // Row 2: Restart, Shutdown
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(DesignTokens.SpaceSM)
            ) {
                SecondaryActionButton(
                    text = "Restart",
                    onClick = { onPower(PowerAction.RESTART) },
                    modifier = Modifier.weight(1f)
                )
                DestructiveActionButton(
                    text = "Shutdown",
                    onClick = { onPower(PowerAction.SHUTDOWN) },
                    modifier = Modifier.weight(1f)
                )
            }
        }
    }
}

/** Lock card showing PIN lock state and controls */
@Composable
private fun LockCard(c: RemoteController) {
    var showPinDialog by remember { mutableStateOf(false) }
    val state = c.lockState
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    AppCard(Modifier.fillMaxWidth(), padding = DesignTokens.SpaceLG) {
        Column(verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceLG)) {
            SectionHeader("PIN Lock")
            Spacer(Modifier.height(DesignTokens.SpaceXS))

            Text(
                when {
                    state == null -> "Loading…"
                    state.locked -> "Locked. Stays locked through sleep, restart and shutdown."
                    state.pinSet -> "Unlocked. Won't lock again until you lock it here."
                    else -> "Set a PIN first to turn this on."
                },
                style = typo.bodySmall,
                color = colors.onSurfaceVariant
            )

            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(DesignTokens.SpaceSM)
            ) {
                if (state?.locked == true) {
                    PrimaryActionButton(
                        text = "Unlock",
                        onClick = { c.unlockPc() },
                        modifier = Modifier.weight(1f)
                    )
                } else {
                    SecondaryActionButton(
                        text = "Lock Now",
                        onClick = { c.lockPc() },
                        modifier = Modifier.weight(1f),
                        enabled = state?.pinSet == true
                    )
                }
                OutlineActionButton(
                    text = if (state?.pinSet == true) "Change PIN" else "Set PIN",
                    onClick = { showPinDialog = true },
                    modifier = Modifier.weight(1f)
                )
            }
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
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    AlertDialog(
        onDismissRequest = { if (!saving) onDismiss() },
        title = { Text("Set unlock PIN", style = typo.titleLarge, color = colors.onSurface) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceMD)) {
                Text(
                    "4-12 digits. Used to unlock at the PC itself.",
                    style = typo.bodySmall, color = colors.onSurfaceVariant
                )
                OutlinedTextField(
                    value = pin,
                    onValueChange = {
                        if (it.length <= 12) {
                            pin = it.filter(Char::isDigit)
                            error = ""
                        }
                    },
                    label = { Text("PIN") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    visualTransformation = androidx.compose.foundation.text.PasswordVisualTransformation(),
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                        keyboardType = androidx.compose.ui.text.input.KeyboardType.Number,
                        imeAction = androidx.compose.foundation.text.ImeAction.Done
                    )
                )
                if (error.isNotBlank()) {
                    Text(error, color = colors.error, style = typo.bodySmall)
                }
            }
        },
        confirmButton = {
            TextButton(
                enabled = valid && !saving,
                onClick = {
                    saving = true
                    onSave(pin) { ok, message -> saving = false; if (ok) onDismiss() else error = message }
                }
            ) {
                Text(if (saving) "Saving…" else "Save", style = typo.labelLarge, color = colors.primary)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !saving) {
                Text("Cancel", style = typo.labelLarge, color = colors.onSurfaceVariant)
            }
        },
        properties = androidx.compose.material3.DialogProperties(usePlatformDefaultWidth = false)
    )
}

/** Live screen controls: quality picker and start session button */
@Composable
private fun LiveScreenSection(c: RemoteController) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    AppCard(Modifier.fillMaxWidth(), padding = DesignTokens.SpaceLG) {
        Column(verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceLG)) {
            SectionHeader("Live Screen")
            Spacer(Modifier.height(DesignTokens.SpaceXS))

            Text(
                "Touch, trackpad and keyboard control of the logged-in desktop.",
                style = typo.bodySmall, color = colors.onSurfaceVariant
            )

            // Quality selector
            Column(
                Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceSM)
            ) {
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Quality", style = typo.labelLarge, color = colors.onSurfaceVariant)
                    // Current quality badge
                    StatusBadge(
                        text = c.quality.label,
                        color = colors.primary
                    )
                }
                QualityPicker(c.quality, { c.setQuality(it) })
                Text(c.quality.hint, style = typo.bodySmall, color = colors.onSurfaceVariant)
            }

            // Start screen session button
            PrimaryActionButton(
                text = "Start Screen Session",
                onClick = { c.startScreen() },
                modifier = Modifier.fillMaxWidth(),
                icon = { Text("▶", style = typo.labelLarge) }
            )
        }
    }
}

/** Notice banner for errors and info */
@Composable
private fun NoticeBanner(notice: Notice) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    val (bgColor, textColor) = if (notice.isError) {
        colors.errorContainer to colors.onErrorContainer
    } else {
        colors.primaryContainer to colors.onPrimaryContainer
    }

    Box(
        Modifier
            .fillMaxWidth()
            .padding(DesignTokens.SpaceMD)
            .background(bgColor, MaterialTheme.shapes.medium)
    ) {
        Text(
            notice.text,
            style = typo.bodySmall,
            color = textColor,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(DesignTokens.SpaceSM)
        )
    }
}