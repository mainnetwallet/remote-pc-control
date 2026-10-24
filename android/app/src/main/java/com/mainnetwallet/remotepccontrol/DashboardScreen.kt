package com.mainnetwallet.remotepccontrol

import androidx.compose.animation.core.animateFloatAsState
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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
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
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).screenInsets().padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Column(Modifier.widthIn(max = 560.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            // Header
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        StatusDot(if (c.reachable) Palette.Good else Palette.Bad)
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (c.reachable) "Connected" else "Offline, retrying",
                            style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Text(status?.hostname ?: "Windows PC", style = MaterialTheme.typography.headlineSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (status != null) Text(
                        "Up ${formatUptime(status.uptimeSeconds)}",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                OutlinedButton(onClick = { c.disconnect() }, contentPadding = compactPadding) { Text("Log out") }
            }

            // CPU / RAM / disk
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                GaugeCard("CPU", status?.cpu, "Processor load", Modifier.weight(1f))
                GaugeCard("Memory", status?.memory, status?.let { "${gb(it.memUsed)} / ${gb(it.memTotal)}" } ?: "-", Modifier.weight(1f))
                GaugeCard("Disk", status?.disk, status?.let { "${gb(it.diskUsed)} / ${gb(it.diskTotal)}" } ?: "-", Modifier.weight(1f))
            }

            // Network
            AppCard(Modifier.fillMaxWidth()) {
                Text("Network", style = MaterialTheme.typography.titleSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(8.dp))
                Row(Modifier.fillMaxWidth()) {
                    RateColumn("Download", status?.rxPerSec, Modifier.weight(1f))
                    RateColumn("Upload", status?.txPerSec, Modifier.weight(1f))
                }
            }

            // Power
            AppCard(Modifier.fillMaxWidth()) {
                Text("Power", style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(12.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    FilledTonalButton(onClick = { onPower(PowerAction.LOCK) }, modifier = Modifier.weight(1f).height(48.dp)) { Text("Lock") }
                    FilledTonalButton(onClick = { onPower(PowerAction.SLEEP) }, modifier = Modifier.weight(1f).height(48.dp)) { Text("Sleep") }
                }
                Spacer(Modifier.height(10.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    FilledTonalButton(onClick = { onPower(PowerAction.RESTART) }, modifier = Modifier.weight(1f).height(48.dp)) { Text("Restart") }
                    Button(
                        onClick = { onPower(PowerAction.SHUTDOWN) }, modifier = Modifier.weight(1f).height(48.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer, contentColor = MaterialTheme.colorScheme.onErrorContainer
                        )
                    ) { Text("Shutdown") }
                }
            }

            // Secure Windows unlock (optional; disabled on the PC until configured, see docs/UNLOCK.md)
            UnlockCard(c)

            // Live screen
            AppCard(Modifier.fillMaxWidth()) {
                Text("Live screen", style = MaterialTheme.typography.titleMedium)
                Spacer(Modifier.height(4.dp))
                Text(
                    "Touch, trackpad and keyboard control of the logged-in desktop.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(14.dp))
                Text("Quality", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(6.dp))
                QualityPicker(c.quality, { c.setQuality(it) })
                Spacer(Modifier.height(6.dp))
                Text(c.quality.hint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(14.dp))
                Button(onClick = { c.startScreen() }, modifier = Modifier.fillMaxWidth().height(52.dp)) { Text("Start screen session") }
            }

            if (c.notice.text.isNotBlank()) Text(
                c.notice.text, style = MaterialTheme.typography.bodySmall,
                color = if (c.notice.isError) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary,
                modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center
            )
            Spacer(Modifier.height(8.dp))
        }
    }
}

private fun gb(bytes: Long): String = String.format(Locale.US, "%.1f GB", bytes / (1024.0 * 1024.0 * 1024.0))

@Composable
private fun RateColumn(label: String, bytesPerSec: Long?, modifier: Modifier) {
    Column(modifier) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(if (bytesPerSec == null) "-" else formatBytes(bytesPerSec) + "/s", style = MaterialTheme.typography.titleLarge)
    }
}

@Composable
private fun GaugeCard(label: String, percent: Int?, detail: String, modifier: Modifier) {
    val color = when {
        percent == null -> MaterialTheme.colorScheme.primary
        percent >= 90 -> Palette.Bad
        percent >= 70 -> Palette.Warn
        else -> MaterialTheme.colorScheme.primary
    }
    AppCard(modifier, padding = 12.dp) {
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            RingGauge(percent, color)
            Spacer(Modifier.height(8.dp))
            Text(label, style = MaterialTheme.typography.titleSmall)
            Text(
                detail, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center
            )
        }
    }
}

@Composable
private fun RingGauge(percent: Int?, color: Color) {
    val track = MaterialTheme.colorScheme.outlineVariant
    val fraction by animateFloatAsState(targetValue = (percent ?: 0).coerceIn(0, 100) / 100f, label = "gauge")
    Box(Modifier.size(72.dp), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = 7.dp.toPx()
            val topLeft = Offset(stroke / 2, stroke / 2)
            val arc = Size(size.width - stroke, size.height - stroke)
            drawArc(track, 0f, 360f, false, topLeft = topLeft, size = arc, style = Stroke(width = stroke))
            if (fraction > 0f) drawArc(color, -90f, 360f * fraction, false, topLeft = topLeft, size = arc, style = Stroke(width = stroke, cap = StrokeCap.Round))
        }
        Text(if (percent == null) "-" else "$percent%", style = MaterialTheme.typography.titleMedium)
    }
}
