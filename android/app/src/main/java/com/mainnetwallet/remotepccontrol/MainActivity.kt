package com.mainnetwallet.remotepccontrol

import android.content.Context
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.animation.Crossfade
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Draw behind the system bars; every screen applies the window insets itself (see screenInsets()).
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
            navigationBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT)
        )
        setContent { RemotePcTheme { RemotePcApp() } }
    }
}

private enum class Page { CONNECT, DASHBOARD, SESSION }

private const val STATUS_REFRESH_MS = 5_000L

@Composable
private fun RemotePcApp() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    // The activity is not recreated on rotation (manifest configChanges), so this state and the sockets survive it.
    val c = remember { RemoteController(scope, context.getSharedPreferences("remote_pc", Context.MODE_PRIVATE)) }
    var confirm by remember { mutableStateOf<PowerAction?>(null) }
    val view = LocalView.current

    DisposableEffect(c.screenOpen) { view.keepScreenOn = c.screenOpen; onDispose { view.keepScreenOn = false } }
    DisposableEffect(Unit) { onDispose { c.shutdown() } }
    // Keep the dashboard numbers fresh while it is on screen.
    LaunchedEffect(c.connected, c.screenOpen) {
        if (c.connected && !c.screenOpen) while (true) { delay(STATUS_REFRESH_MS); c.refreshStatus() }
    }
    BackHandler(enabled = c.screenOpen) { c.stopScreen() }

    confirm?.let { action ->
        AlertDialog(
            onDismissRequest = { confirm = null },
            title = { Text(action.confirmTitle) },
            text = { Text(action.confirmBody) },
            confirmButton = { TextButton(onClick = { confirm = null; c.power(action) }) { Text(action.label) } },
            dismissButton = { TextButton(onClick = { confirm = null }) { Text("Cancel") } }
        )
    }

    Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        val page = when {
            c.screenOpen -> Page.SESSION
            c.connected -> Page.DASHBOARD
            else -> Page.CONNECT
        }
        Crossfade(targetState = page, label = "page") { p ->
            when (p) {
                Page.CONNECT -> ConnectScreen(c)
                Page.DASHBOARD -> DashboardScreen(c) { action -> if (action.needsConfirm) { confirm = action } else { c.power(action) } }
                Page.SESSION -> SessionScreen(c)
            }
        }
    }
}
