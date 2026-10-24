package com.mainnetwallet.remotepccontrol

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.tween
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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale

/** Keeps content clear of the status bar, navigation bar and display cutout (the app draws edge to edge). */
fun Modifier.screenInsets(): Modifier = systemBarsPadding().displayCutoutPadding()

val compactPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
/** Smaller padding for the compact buttons inside the landscape Controls menu (32 dp high). */
val menuPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp)

@Composable
fun AppCard(
    modifier: Modifier = Modifier,
    padding: Dp = 16.dp,
    elevation: Dp = 0.dp,
    content: @Composable ColumnScope.() -> Unit
) {
    val colors = MaterialTheme.colorScheme
    val shapes = MaterialTheme.shapes

    Card(
        modifier = modifier
            .shadow(elevation, shape = shapes.large),
        shape = shapes.large,
        colors = CardDefaults.cardColors(
            containerColor = colors.surface,
            // Subtle border for definition
            surfaceTint = colors.surfaceContainerHigh
        ),
        border = BorderStroke(1.dp, colors.outlineVariant)
    ) {
        Column(
            Modifier
                .padding(padding)
                .fillMaxWidth(),
            content = content
        )
    }
}

/** Elevated card variant for primary content */
@Composable
fun ElevatedCard(
    modifier: Modifier = Modifier,
    padding: Dp = 16.dp,
    content: @Composable ColumnScope.() -> Unit
) {
    val colors = MaterialTheme.colorScheme
    val shapes = MaterialTheme.shapes

    Card(
        modifier = modifier
            .shadow(4.dp, shape = shapes.large),
        shape = shapes.large,
        colors = CardDefaults.cardColors(
            containerColor = colors.surfaceContainer,
            surfaceTint = colors.surfaceContainerHigh
        )
    ) {
        Column(
            Modifier
                .padding(padding)
                .fillMaxWidth(),
            content = content
        )
    }
}

/** Outlined card variant for subtle sections */
@Composable
fun OutlinedCard(
    modifier: Modifier = Modifier,
    padding: Dp = 16.dp,
    content: @Composable ColumnScope.() -> Unit
) {
    val colors = MaterialTheme.colorScheme
    val shapes = MaterialTheme.shapes

    Card(
        modifier = modifier,
        shape = shapes.large,
        colors = CardDefaults.cardColors(containerColor = colors.surface),
        border = BorderStroke(1.dp, colors.outline)
    ) {
        Column(
            Modifier
                .padding(padding)
                .fillMaxWidth(),
            content = content
        )
    }
}

@Composable
fun StatusDot(color: Color, modifier: Modifier = Modifier, size: Dp = 8.dp) {
    Box(
        modifier
            .size(size)
            .background(color, CircleShape)
            .shadow(2.dp, CircleShape)
    )
}

/** Pulsing status indicator for connected state */
@Composable
fun PulsingStatusDot(
    color: Color,
    modifier: Modifier = Modifier,
    size: Dp = 10.dp,
    enabled: Boolean = true
) {
    val alpha by animateFloatAsState(
        targetValue = if (enabled) 1f else 0.5f,
        animationSpec = tween(1500, delayMillis = 0, easing = { it })
    )
    val scale by animateFloatAsState(
        targetValue = if (enabled) 1.2f else 1f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessLow)
    )

    Box(
        modifier
            .size(size)
            .graphicsLayer { this.alpha = alpha; this.scaleX = scale; this.scaleY = scale }
            .background(color, CircleShape)
    )
}

@Composable
fun SectionHeader(
    title: String,
    modifier: Modifier = Modifier,
    action: (@Composable () -> Unit)? = null
) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(title, style = typo.titleMedium, color = colors.onSurface)
        action?.invoke()
    }
}

@Composable
fun MetricLabel(
    label: String,
    modifier: Modifier = Modifier
) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    Text(
        label,
        style = typo.labelMedium,
        color = colors.onSurfaceVariant,
        modifier = modifier
    )
}

@Composable
fun MetricValue(
    value: String,
    modifier: Modifier = Modifier,
    color: Color? = null
) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    Text(
        value,
        style = typo.headlineSmall,
        color = color ?: colors.onSurface,
        modifier = modifier,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis
    )
}

@Composable
fun MetricDetail(
    detail: String,
    modifier: Modifier = Modifier
) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    Text(
        detail,
        style = typo.bodySmall,
        color = colors.onSurfaceVariant,
        modifier = modifier,
        maxLines = 1,
        overflow = TextOverflow.Ellipsis
    )
}

/** Row of quality options with refined styling */
@Composable
fun QualityPicker(
    selected: Quality,
    onSelect: (Quality) -> Unit,
    modifier: Modifier = Modifier
) {
    val colors = MaterialTheme.colorScheme
    val shape = MaterialTheme.shapes.medium
    val typo = MaterialTheme.typography

    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(DesignTokens.SpaceSM)
    ) {
        Quality.values().forEach { q ->
            val isSelected = q == selected
            Box(
                Modifier
                    .weight(1f)
                    .height(DesignTokens.TouchTargetComfortable)
                    .clip(shape)
                    .background(
                        if (isSelected) colors.primaryContainer else colors.surfaceVariant
                    )
                    .border(
                        if (isSelected) 2.dp else 1.dp,
                        if (isSelected) colors.primary else colors.outlineVariant,
                        shape
                    )
                    .selectable(
                        selected = isSelected,
                        role = Role.RadioButton,
                        onClick = { onSelect(q) }
                    )
                    .animateContentSize(),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    q.label,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    style = typo.labelLarge,
                    color = if (isSelected) colors.onPrimaryContainer else colors.onSurfaceVariant
                )
            }
        }
    }
}

/** Compact "Quality: Medium" button with a drop-down, used in the session toolbars. */
@Composable
fun QualityMenuButton(
    quality: Quality,
    onSelect: (Quality) -> Unit,
    modifier: Modifier = Modifier,
    compact: Boolean = false
) {
    var expanded by remember { mutableStateOf(false) }
    Box(modifier) {
        if (compact) FilledTonalButton(
            onClick = { expanded = true },
            modifier = Modifier.fillMaxWidth().height(36.dp),
            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 0.dp)
        ) {
            Text("Quality: ${quality.label}", style = MaterialTheme.typography.labelMedium, maxLines = 1)
        }
        else FilledTonalButton(onClick = { expanded = true }, contentPadding = compactPadding) {
            Text("Quality: ${quality.label}")
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            Quality.values().forEach { q ->
                DropdownMenuItem(
                    text = {
                        Column {
                            Text(
                                if (q == quality) "${q.label}  ✓" else q.label,
                                style = MaterialTheme.typography.titleSmall
                            )
                            Text(q.hint, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    },
                    onClick = { expanded = false; onSelect(q) }
                )
            }
        }
    }
}

@Composable
fun GaugeCard(
    label: String,
    percent: Int?,
    detail: String,
    modifier: Modifier,
    showAnimation: Boolean = true
) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    val gaugeColor = when {
        percent == null -> colors.primary
        percent >= 90 -> Palette.Danger
        percent >= 70 -> Palette.Warning
        else -> Palette.Success
    }

    AppCard(modifier, padding = 12.dp) {
        Column(
            Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceSM)
        ) {
            RingGauge(percent, gaugeColor, showAnimation)
            Text(label, style = typo.titleSmall, color = colors.onSurface)
            Text(
                detail,
                style = typo.labelSmall,
                color = colors.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                textAlign = TextAlign.Center
            )
        }
    }
}

@Composable
fun RingGauge(
    percent: Int?,
    color: Color,
    animate: Boolean = true
) {
    val trackColor = MaterialTheme.colorScheme.outlineVariant
    val targetFraction = (percent ?: 0).coerceIn(0, 100) / 100f

    val fraction by animateFloatAsState(
        targetValue = targetFraction,
        label = "gauge",
        animationSpec = if (animate) spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessMedium) else null
    )

    Box(
        Modifier.size(DesignTokens.GaugeSize),
        contentAlignment = Alignment.Center
    ) {
        Canvas(Modifier.fillMaxSize()) {
            val stroke = DesignTokens.GaugeStroke.toPx()
            val topLeft = Offset(stroke / 2, stroke / 2)
            val arc = Size(size.width - stroke, size.height - stroke)

            // Track
            drawArc(
                trackColor, 0f, 360f, false,
                topLeft = topLeft, size = arc,
                style = Stroke(width = stroke, cap = StrokeCap.Round)
            )

            // Progress
            if (fraction > 0f) {
                drawArc(
                    color, -90f, 360f * fraction, false,
                    topLeft = topLeft, size = arc,
                    style = Stroke(width = stroke, cap = StrokeCap.Round)
                )
            }
        }

        Text(
            if (percent == null) "–" else "$percent%",
            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold),
            color = if (percent == null) MaterialTheme.colorScheme.onSurfaceVariant else color
        )
    }
}

@Composable
fun RateColumn(
    label: String,
    bytesPerSec: Long?,
    modifier: Modifier,
    showIcon: Boolean = true
) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    Column(modifier, horizontalAlignment = Alignment.CenterHorizontally) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(DesignTokens.SpaceXS),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (showIcon) {
                Text(
                    if (label == "Download") "⬇" else "⬆",
                    style = typo.labelMedium,
                    color = colors.onSurfaceVariant
                )
            }
            Text(label, style = typo.labelMedium, color = colors.onSurfaceVariant)
        }
        Spacer(Modifier.height(DesignTokens.SpaceXS))
        Text(
            if (bytesPerSec == null) "–" else formatBytes(bytesPerSec) + "/s",
            style = typo.titleLarge,
            color = colors.onSurface,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

fun formatBytes(value: Long): String = when {
    value >= 1024L * 1024L * 1024L -> String.format(Locale.US, "%.1f GB", value / (1024.0 * 1024.0 * 1024.0))
    value >= 1024L * 1024L -> String.format(Locale.US, "%.1f MB", value / (1024.0 * 1024.0))
    value >= 1024L -> String.format(Locale.US, "%.1f KB", value / 1024.0)
    else -> "$value B"
}

fun formatUptime(seconds: Long): String {
    val days = seconds / 86_400
    val hours = (seconds % 86_400) / 3_600
    val minutes = (seconds % 3_600) / 60
    return when {
        days > 0 -> "${days}d ${hours}h"
        hours > 0 -> "${hours}h ${minutes}m"
        else -> "${minutes}m"
    }
}

/** Primary action button with consistent styling */
@Composable
fun PrimaryActionButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    icon: (@Composable () -> Unit)? = null
) {
    val colors = MaterialTheme.colorScheme

    Button(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .height(DesignTokens.TouchTargetLarge),
        enabled = enabled && !loading,
        colors = ButtonDefaults.buttonColors(
            containerColor = colors.primary,
            contentColor = colors.onPrimary,
            disabledContainerColor = colors.surfaceContainerHigh,
            disabledContentColor = colors.onSurfaceVariant
        ),
        shape = MaterialTheme.shapes.medium
    ) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (loading) {
                androidx.compose.material3.CircularProgressIndicator(
                    Modifier.size(20.dp),
                    color = colors.onPrimary,
                    strokeWidth = 2.dp
                )
                Spacer(Modifier.width(DesignTokens.SpaceSM))
            }
            icon?.invoke()
            if (icon != null && !loading) Spacer(Modifier.width(DesignTokens.SpaceSM))
            Text(text, style = MaterialTheme.typography.labelLarge, maxLines = 1)
        }
    }
}

/** Secondary action button */
@Composable
fun SecondaryActionButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true
) {
    val colors = MaterialTheme.colorScheme

    FilledTonalButton(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .height(DesignTokens.TouchTargetLarge),
        enabled = enabled,
        colors = ButtonDefaults.buttonColors(
            containerColor = colors.secondaryContainer,
            contentColor = colors.onSecondaryContainer,
            disabledContainerColor = colors.surfaceContainerHigh,
            disabledContentColor = colors.onSurfaceVariant
        ),
        shape = MaterialTheme.shapes.medium
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, maxLines = 1)
    }
}

/** Destructive action button */
@Composable
fun DestructiveActionButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true
) {
    val colors = MaterialTheme.colorScheme

    Button(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .height(DesignTokens.TouchTargetLarge),
        enabled = enabled,
        colors = ButtonDefaults.buttonColors(
            containerColor = colors.errorContainer,
            contentColor = colors.onErrorContainer,
            disabledContainerColor = colors.surfaceContainerHigh,
            disabledContentColor = colors.onSurfaceVariant
        ),
        shape = MaterialTheme.shapes.medium
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, maxLines = 1)
    }
}

/** Outline action button */
@Composable
fun OutlineActionButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true
) {
    val colors = MaterialTheme.colorScheme

    androidx.compose.material3.OutlinedButton(
        onClick = onClick,
        modifier = modifier
            .fillMaxWidth()
            .height(DesignTokens.TouchTargetLarge),
        enabled = enabled,
        colors = ButtonDefaults.outlinedButtonColors(
            containerColor = colors.surface,
            contentColor = colors.primary,
            disabledContentColor = colors.onSurfaceVariant,
            outlineColor = colors.outlineVariant
        ),
        shape = MaterialTheme.shapes.medium
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, maxLines = 1)
    }
}

/** Divider with subtle styling */
@Composable
fun SubtleDivider(modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    androidx.compose.foundation.Divider(
        modifier = modifier.fillMaxWidth(),
        color = colors.outlineVariant,
        thickness = 1.dp
    )
}

/** Status badge for connection state */
@Composable
fun StatusBadge(
    text: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    val colors = MaterialTheme.colorScheme

    Box(
        modifier
            .padding(horizontal = DesignTokens.SpaceSM, vertical = DesignTokens.SpaceXS)
            .background(color.copy(alpha = 0.15f), MaterialTheme.shapes.small)
            .border(1.dp, color.copy(alpha = 0.4f), MaterialTheme.shapes.small)
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelSmall,
            color = color
        )
    }
}

/** Empty state placeholder */
@Composable
fun EmptyState(
    icon: @Composable () -> Unit,
    title: String,
    subtitle: String? = null,
    action: (@Composable () -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    val colors = MaterialTheme.colorScheme
    val typo = MaterialTheme.typography

    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(DesignTokens.Space3XL),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(DesignTokens.SpaceMD)
    ) {
        Box(
            Modifier.size(64.dp),
            contentAlignment = Alignment.Center
        ) {
            icon()
        }
        Text(title, style = typo.titleMedium, color = colors.onSurface, textAlign = TextAlign.Center)
        subtitle?.let {
            Text(it, style = typo.bodyMedium, color = colors.onSurfaceVariant, textAlign = TextAlign.Center)
        }
        action?.invoke()
    }
}