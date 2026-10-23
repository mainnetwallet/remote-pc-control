package com.mainnetwallet.remotepccontrol

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.unit.dp
import org.json.JSONArray
import org.json.JSONObject

/** One key of the on-screen PC keyboard. key == null is an empty gap; "#CLOSE" hides the keyboard. */
private class K(val label: String, val key: String?, val w: Float = 1f)

private fun chars(s: String) = s.map { K(if (it.isLetter()) it.uppercase() else it.toString(), it.toString()) }

// Every row adds up to 16 width units, so the keys line up like on a real keyboard.
private val KEY_ROWS: List<List<K>> = listOf(
    listOf(K("Esc", "ESC", 1.5f)) + (1..12).map { K("F$it", "F$it") } + listOf(K("Del", "DELETE", 1.5f), K("\u2715", "#CLOSE")),
    chars("`1234567890-=") + K("Bksp", "BACKSPACE", 3f),
    listOf(K("Tab", "TAB", 2f)) + chars("qwertyuiop[]") + K("\\", "\\", 2f),
    listOf(K("", null, 2f)) + chars("asdfghjkl;'") + K("Enter", "ENTER", 3f),
    listOf(K("Shift", "SHIFT", 3f)) + chars("zxcvbnm,./") + K("Shift", "SHIFT", 3f),
    listOf(
        K("Ctrl", "CTRL", 1.5f), K("Win", "WIN", 1.5f), K("Alt", "ALT", 1.5f), K("Space", "SPACE", 7.5f),
        K("\u2190", "LEFT"), K("\u2191", "UP"), K("\u2193", "DOWN"), K("\u2192", "RIGHT")
    )
)

/**
 * PC-style on-screen keyboard. Ctrl, Alt, Win and Shift are sticky: tap them, then tap a key, and the PC gets the
 * whole combination (Ctrl then A = Ctrl+A). Plain keys are sent as single key presses.
 */
@Composable
fun PcKeyboard(send: (JSONObject) -> Unit, onClose: () -> Unit, modifier: Modifier = Modifier) {
    var ctrl by remember { mutableStateOf(false) }
    var alt by remember { mutableStateOf(false) }
    var win by remember { mutableStateOf(false) }
    var shift by remember { mutableStateOf(false) }

    fun fire(key: String) {
        val mods = buildList { if (ctrl) add("CTRL"); if (alt) add("ALT"); if (win) add("WIN"); if (shift) add("SHIFT") }.take(3)
        if (mods.isEmpty()) send(JSONObject().put("type", "key").put("key", key))
        else send(JSONObject().put("type", "hotkey").put("keys", JSONArray(mods + key)))
        ctrl = false; alt = false; win = false; shift = false   // modifiers apply to one key, then release
    }

    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(3.dp)) {
        KEY_ROWS.forEach { row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                row.forEach { k ->
                    val key = k.key
                    if (key == null) Spacer(Modifier.weight(k.w))
                    else {
                        val active = when (key) { "CTRL" -> ctrl; "ALT" -> alt; "WIN" -> win; "SHIFT" -> shift; else -> false }
                        KeyCap(k.label, k.w, active) {
                            when (key) {
                                "CTRL" -> ctrl = !ctrl
                                "ALT" -> alt = !alt
                                "WIN" -> win = !win
                                "SHIFT" -> shift = !shift
                                "#CLOSE" -> onClose()
                                else -> fire(key)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RowScope.KeyCap(label: String, weight: Float, active: Boolean, onClick: () -> Unit) {
    val scheme = MaterialTheme.colorScheme
    Box(
        Modifier.weight(weight).height(34.dp).clip(RoundedCornerShape(6.dp))
            .background(if (active) scheme.primary else scheme.secondaryContainer)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Text(
            label, style = MaterialTheme.typography.labelSmall, maxLines = 1,
            color = if (active) scheme.onPrimary else scheme.onSecondaryContainer
        )
    }
}
