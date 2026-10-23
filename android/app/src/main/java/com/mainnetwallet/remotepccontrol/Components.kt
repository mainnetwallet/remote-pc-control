package com.mainnetwallet.remotepccontrol

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.displayCutoutPadding
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import java.util.Locale

/** Keeps content clear of the status bar, navigation bar and display cutout (the app draws edge to edge). */
fun Modifier.screenInsets(): Modifier = systemBarsPadding().displayCutoutPadding()

val compactPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
/** Smaller padding for the compact buttons inside the landscape Controls menu (32 dp high). */
val menuPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)

@Composable
fun AppCard(modifier: Modifier = Modifier, padding: Dp = 16.dp, content: @Composable ColumnScope.() -> Unit) {
    Card(
        modifier = modifier,
        shape = MaterialTheme.shapes.large,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
    ) { Column(Modifier.padding(padding), content = content) }
}

@Composable
fun StatusDot(color: Color, modifier: Modifier = Modifier) {
    Box(modifier.size(8.dp).background(color, CircleShape))
}

/** Row of four selectable pills: Low / Medium / High / Native. */
@Composable
fun QualityPicker(selected: Quality, onSelect: (Quality) -> Unit, modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(12.dp)
    Row(modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Quality.values().forEach { q ->
            val on = q == selected
            Box(
                Modifier.weight(1f).height(44.dp)
                    .clip(shape)
                    .background(if (on) colors.primaryContainer else colors.surfaceVariant)
                    .border(1.dp, if (on) colors.primary else colors.outlineVariant, shape)
                    .selectable(selected = on, role = Role.RadioButton, onClick = { onSelect(q) }),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    q.label, maxLines = 1, overflow = TextOverflow.Ellipsis,
                    style = MaterialTheme.typography.labelLarge,
                    color = if (on) colors.onPrimaryContainer else colors.onSurfaceVariant
                )
            }
        }
    }
}

/** Compact "Quality: Medium" button with a drop-down, used in the session toolbars. */
@Composable
fun QualityMenuButton(quality: Quality, onSelect: (Quality) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Box {
        FilledTonalButton(onClick = { expanded = true }, contentPadding = compactPadding) { Text("Quality: ${quality.label}") }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            Quality.values().forEach { q ->
                DropdownMenuItem(
                    text = {
                        Column {
                            Text(if (q == quality) "${q.label}  ✓" else q.label, style = MaterialTheme.typography.titleSmall)
                            Text(q.hint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    },
                    onClick = { expanded = false; onSelect(q) }
                )
            }
        }
    }
}

fun formatBytes(value: Long): String = when {
    value >= 1024L * 1024L * 1024L -> String.format(Locale.US, "%.1f GB", value / (1024.0 * 1024.0 * 1024.0))
    value >= 1024L * 1024L -> String.format(Locale.US, "%.1f MB", value / (1024.0 * 1024.0))
    value >= 1024L -> String.format(Locale.US, "%.1f KB", value / 1024.0)
    else -> "$value B"
}

fun formatUptime(seconds: Long): String {
    val days = seconds / 86_400; val hours = (seconds % 86_400) / 3_600; val minutes = (seconds % 3_600) / 60
    return when {
        days > 0 -> "${days}d ${hours}h"
        hours > 0 -> "${hours}h ${minutes}m"
        else -> "${minutes}m"
    }
}
