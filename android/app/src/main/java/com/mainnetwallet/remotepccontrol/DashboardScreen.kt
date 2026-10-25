package com.mainnetwallet.remotepccontrol

import android.content.Context
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.displayCutoutPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

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

/**
 * The signed-in shell: a page (Home dashboard or Settings) above a three-item bottom bar.
 * "PC Live" is not a page of its own: it starts the existing screen session, which MainActivity then shows
 * full screen (with its own toolbar and the Back-to-stop behaviour), so the session logic exists only once.
 */
@Composable
fun DashboardScreen(c: RemoteController, onPower: (PowerAction) -> Unit) {
    var tab by rememberSaveable { mutableStateOf(NavTab.HOME.name) }
    val current = NavTab.valueOf(tab)
    val history = remember { MetricHistory() }
    // Every fresh status reading adds one point to the trend lines.
    LaunchedEffect(c.status) { c.status?.let { history.add(it) } }
    // Back from Settings returns to Home instead of leaving the app.
    BackHandler(enabled = current == NavTab.SETTINGS) { tab = NavTab.HOME.name }

    // A real Scaffold bottomBar: the bar is measured first and the page gets its height as content padding, so the
    // page (and its scroll area) always ends exactly where the bar starts and can never run underneath it.
    // The bar applies the navigation-bar inset itself; each page applies the status-bar/cutout inset at its top.
    Scaffold(
        modifier = Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(DashColors.BgTop, DashColors.BgBottom))),
        containerColor = Color.Transparent,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            DashBottomNav(selected = current) { picked ->
                when (picked) {
                    NavTab.LIVE -> c.startScreen()      // the same call the Start Screen Session button makes
                    else -> tab = picked.name
                }
            }
        }
    ) { inner ->
        // Everything inside is clipped to the area above the bar: nothing from a page can be drawn under it.
        Box(Modifier.padding(inner).fillMaxSize().clipToBounds()) {
            when (current) {
                NavTab.SETTINGS -> SettingsPage(c)
                else -> HomePage(c, history, onPower)
            }
        }
    }
}

@Composable
private fun HomePage(c: RemoteController, history: MetricHistory, onPower: (PowerAction) -> Unit) {
    val status = c.status
    val scroll = rememberScrollState()
    Box(Modifier.fillMaxSize()) {
    Column(
        Modifier.fillMaxSize().verticalScroll(scroll).statusBarsPadding().displayCutoutPadding().padding(start = 12.dp, end = 12.dp, top = 2.dp, bottom = 8.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Column(Modifier.widthIn(max = 560.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(5.dp)) {
            DashConnectionHeader(
                hostname = status?.hostname ?: "Windows PC",
                reachable = c.reachable,
                uptime = status?.let { "Up ${formatUptime(it.uptimeSeconds)}" },
                address = connectionAddress(c.baseUrl)
            )

            // Live screen directly under the header: pick the quality, then start the session.
            DashPanel(Modifier.fillMaxWidth()) {
                DashSectionHeader(Glyph.MONITOR, "Live Screen") {
                    DashChip(Glyph.MONITOR, resolutionText(c.quality))
                }
                Spacer(Modifier.height(6.dp))
                DashPresetSelector(c.quality, { c.setQuality(it) })
                Spacer(Modifier.height(3.dp))
                Text(c.quality.hint, style = MaterialTheme.typography.labelSmall, color = DashColors.Muted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Spacer(Modifier.height(5.dp))
                DashPrimaryButton("Start Screen Session", Glyph.PLAY, { c.startScreen() }, Modifier.fillMaxWidth())
            }

            DashSystemPanel(status, c.reachable, history, Modifier.fillMaxWidth())

            // Power: four tiles in one row (two rows on very narrow phones). Same callback as before;
            // the confirmation dialogs live in MainActivity.
            DashPanel(Modifier.fillMaxWidth()) {
                DashSectionHeader(Glyph.BOLT, "Quick Actions", DashColors.Cyan)
                Spacer(Modifier.height(6.dp))
                BoxWithConstraints(Modifier.fillMaxWidth()) {
                    val perRow = if (maxWidth < 300.dp) 2 else 4
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        PowerAction.values().toList().chunked(perRow).forEach { group ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                group.forEach { action ->
                                    DashPowerTile(
                                        label = action.label, subtitle = action.subtitle(), glyph = action.glyph(), tint = action.tint(),
                                        onClick = { onPower(action) }, modifier = Modifier.weight(1f)
                                    )
                                }
                            }
                        }
                    }
                }
            }

            PinSecurityCard(c)

            if (c.notice.text.isNotBlank()) DashNotice(c.notice.text, c.notice.isError)
        }
    }
    // A soft fade at the bottom edge while there is more to scroll to, so a card cut off at the fold reads as
    // "scroll for more" and not as hidden behind the bar. It does not take touches.
    if (scroll.canScrollForward) Box(
        Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(28.dp)
            .background(Brush.verticalGradient(listOf(Color.Transparent, DashColors.BgBottom)))
    )
    }
}

/** The address the app connects to, without scheme or port noise for Gist references. Real, from the saved setting. */
private fun connectionAddress(baseUrl: String): String {
    val t = baseUrl.trim().removePrefix("http://").removePrefix("https://").trimEnd('/')
    return if (t.startsWith("gist:") || t.contains("gist.github.com")) "" else t.substringBefore(':')
}

/** Resolution information straight from the selected preset: its maximum frame width (0 = the PC's own size). */
private fun resolutionText(q: Quality): String = if (q.maxWidth == 0) "Native size" else "${q.maxWidth} px wide"

private fun PowerAction.glyph(): Glyph = when (this) {
    PowerAction.LOCK -> Glyph.LOCK
    PowerAction.SLEEP -> Glyph.MOON
    PowerAction.RESTART -> Glyph.RESTART
    PowerAction.SHUTDOWN -> Glyph.POWER
}

private fun PowerAction.subtitle(): String = when (this) {
    PowerAction.LOCK -> "Lock your PC"
    PowerAction.SLEEP -> "Power save"
    PowerAction.RESTART -> "Reboot PC"
    PowerAction.SHUTDOWN -> "Turn off PC"
}

/** Neutral icons; only the destructive shutdown action is tinted (red). */
private fun PowerAction.tint(): Color = when (this) {
    PowerAction.LOCK, PowerAction.SLEEP, PowerAction.RESTART -> DashColors.Neutral
    PowerAction.SHUTDOWN -> DashColors.Red
}

/**
 * The PC's always-on PIN screen (separate from the Windows "Lock" action above: this one stays locked
 * permanently -- through sleep, restart and shutdown -- until unlocked here or with the PIN at the PC itself).
 * The lock logic and callbacks are unchanged from the previous dashboard.
 */
@Composable
private fun PinSecurityCard(c: RemoteController) {
    var showPinDialog by remember { mutableStateOf(false) }
    val state = c.lockState
    val badgeText: String
    val badgeColor: Color
    val title: String
    val subtitle: String
    when {
        state == null -> { badgeText = "Checking…"; badgeColor = DashColors.Muted; title = "Checking PIN lock"; subtitle = "Reading the lock state from the PC" }
        state.locked -> { badgeText = "Locked"; badgeColor = DashColors.Amber; title = "Your PC is PIN-locked"; subtitle = "Unlock it here or with the PIN at the PC" }
        state.pinSet -> { badgeText = "Unlocked"; badgeColor = DashColors.Green; title = "Your PC is accessible"; subtitle = "No PIN lock is active" }
        else -> { badgeText = "No PIN set"; badgeColor = DashColors.Muted; title = "No PIN set yet"; subtitle = "Set a PIN to enable locking" }
    }

    DashPanel(Modifier.fillMaxWidth()) {
        DashSectionHeader(Glyph.SHIELD, "PIN Security") {
            DashStatusPill(badgeText, badgeColor, pulsing = false, glyph = Glyph.LOCK)
        }
        Spacer(Modifier.height(6.dp))
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(38.dp).clip(CircleShape).background(badgeColor.copy(alpha = 0.22f)), contentAlignment = Alignment.Center) {
                    DashIcon(Glyph.LOCK, badgeColor, iconSize = 21.dp)
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text(title, style = MaterialTheme.typography.titleSmall, maxLines = 2)
                    Text(subtitle, style = MaterialTheme.typography.labelMedium, color = DashColors.Muted, maxLines = 2)
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (state?.locked == true) {
                    DashOutlineButton("Unlock", Glyph.LOCK, DashColors.Green, { c.unlockPc() }, Modifier.weight(1f))
                } else {
                    DashOutlineButton("Lock now", Glyph.LOCK, DashColors.Neutral, { c.lockPc() }, Modifier.weight(1f), enabled = state?.pinSet == true)
                }
                DashOutlineButton(if (state?.pinSet == true) "Change PIN" else "Set PIN", Glyph.KEY, DashColors.Neutral, { showPinDialog = true }, Modifier.weight(1f))
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

// ---------------------------------------------------------------------------------------------
// Settings: only things that really work in this app today
// ---------------------------------------------------------------------------------------------

@Composable
private fun SettingsPage(c: RemoteController) {
    val context = LocalContext.current
    val version = remember { appVersion(context) }
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).statusBarsPadding().displayCutoutPadding().padding(horizontal = 12.dp, vertical = 6.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Column(Modifier.widthIn(max = 560.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Settings", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(start = 4.dp, top = 4.dp))

            DashPanel(Modifier.fillMaxWidth()) {
                DashSectionHeader(Glyph.MONITOR, "Connected PC")
                Spacer(Modifier.height(10.dp))
                SettingsRow("Name", c.status?.hostname ?: "Windows PC")
                SettingsRow("Address", c.baseUrl.trim().ifBlank { "–" })
                SettingsRow("Status", if (c.reachable) "Connected" else "Offline")
            }

            // The same preset the Live Screen card uses: stored and applied through the same callback.
            DashPanel(Modifier.fillMaxWidth()) {
                DashSectionHeader(Glyph.PLAY, "Default stream quality")
                Spacer(Modifier.height(6.dp))
                Column(Modifier.selectableGroup()) {
                    Quality.values().forEach { q ->
                        val on = q == c.quality
                        Row(
                            Modifier.fillMaxWidth().selectable(selected = on, role = Role.RadioButton, onClick = { c.setQuality(q) }).padding(vertical = 8.dp, horizontal = 4.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                Modifier.size(20.dp).clip(CircleShape).border(2.dp, if (on) DashColors.Cyan else DashColors.PanelBorder, CircleShape),
                                contentAlignment = Alignment.Center
                            ) { if (on) Box(Modifier.size(10.dp).clip(CircleShape).background(DashColors.Cyan)) }
                            Spacer(Modifier.width(12.dp))
                            Column(Modifier.weight(1f)) {
                                Text("${q.label} · ${q.fpsText}", style = MaterialTheme.typography.titleSmall)
                                Text(q.hint, style = MaterialTheme.typography.labelSmall, color = DashColors.Muted)
                            }
                        }
                    }
                }
            }

            // Trackpad pointer speed: the only place it can be changed. Saved when the finger lifts.
            DashPanel(Modifier.fillMaxWidth()) {
                DashSectionHeader(Glyph.BOLT, "Mouse speed") {
                    DashChip(Glyph.BOLT, String.format(java.util.Locale.US, "%.1fx", c.mouseSpeed))
                }
                Spacer(Modifier.height(6.dp))
                Slider(
                    value = c.mouseSpeed,
                    onValueChange = { c.setMouseSpeed(Math.round(it * 10f) / 10f, save = false) },
                    onValueChangeFinished = { c.setMouseSpeed(c.mouseSpeed) },
                    valueRange = 0.5f..4f,
                    colors = SliderDefaults.colors(
                        thumbColor = DashColors.Blue, activeTrackColor = DashColors.Blue,
                        inactiveTrackColor = DashColors.PanelBorder
                    )
                )
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("How far the pointer moves per finger swipe on the trackpad.", style = MaterialTheme.typography.labelSmall, color = DashColors.Muted, modifier = Modifier.weight(1f))
                    TextButton(onClick = { c.setMouseSpeed(DEFAULT_MOUSE_SPEED) }) { Text("Reset 3.0x") }
                }
            }

            DashPanel(Modifier.fillMaxWidth()) {
                DashSectionHeader(Glyph.GEAR, "Account")
                Spacer(Modifier.height(10.dp))
                DashOutlineButton("Log out", Glyph.LOGOUT, DashColors.Red, { c.disconnect() }, Modifier.fillMaxWidth())
                Spacer(Modifier.height(10.dp))
                Text("Logging out forgets the saved password on this phone.", style = MaterialTheme.typography.labelSmall, color = DashColors.Muted)
                if (version.isNotBlank()) {
                    Spacer(Modifier.height(10.dp))
                    SettingsRow("App version", version)
                }
            }
            Spacer(Modifier.height(2.dp))
        }
    }
}

@Composable
private fun SettingsRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = DashColors.Muted, modifier = Modifier.width(96.dp))
        Text(value, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f), textAlign = TextAlign.End, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

private fun appVersion(context: Context): String = try {
    context.packageManager.getPackageInfo(context.packageName, 0).versionName.orEmpty()
} catch (_: Exception) { "" }
