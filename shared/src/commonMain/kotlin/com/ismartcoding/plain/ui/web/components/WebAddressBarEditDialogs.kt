package com.ismartcoding.plain.ui.web.components

import com.ismartcoding.plain.i18n.*

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import com.ismartcoding.plain.ui.base.PTextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import org.jetbrains.compose.resources.stringResource
import androidx.compose.ui.unit.dp
import com.ismartcoding.plain.ui.components.ButtonSize
import com.ismartcoding.plain.ui.base.PDialogRadioRow
import com.ismartcoding.plain.ui.base.PFilledButton
import com.ismartcoding.plain.ui.base.PTextField
import com.ismartcoding.plain.network.httpPorts
import com.ismartcoding.plain.network.httpsPorts
import com.ismartcoding.plain.ui.theme.dialogSheetBackground

@Composable
fun MdnsAndPortEditDialog(
    isHttps: Boolean,
    currentHostname: String,
    currentPort: Int,
    onDismiss: () -> Unit,
    onSave: (hostname: String, port: Int) -> Unit,
) {
    val ports = if (isHttps) httpsPorts else httpPorts
    var editHostname by remember { mutableStateOf(currentHostname) }
    var selectedPort by remember { mutableStateOf(currentPort) }
    var hostnameError by remember { mutableStateOf(false) }

    AlertDialog(
        modifier = Modifier.fillMaxWidth(),
        containerColor = MaterialTheme.colorScheme.dialogSheetBackground,
        onDismissRequest = onDismiss,
        title = { Text(text = stringResource(Res.string.edit)) },
        text = {
            Column {
                Text(
                    text = stringResource(Res.string.mdns_hostname),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                Spacer(modifier = Modifier.height(8.dp))
                PTextField(
                    readOnly = false,
                    value = editHostname,
                    singleLine = true,
                    onValueChange = {
                        editHostname = it
                        hostnameError = false
                    },
                    placeholder = currentHostname,
                    errorMessage = if (hostnameError) stringResource(Res.string.mdns_hostname_invalid) else "",
                )
                Spacer(modifier = Modifier.height(32.dp))
                Text(
                    text = stringResource(Res.string.change_port),
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
                Spacer(modifier = Modifier.height(4.dp))
                LazyColumn(modifier = Modifier.height(200.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    items(ports.toList()) { p ->
                        PDialogRadioRow(
                            selected = p == selectedPort,
                            onClick = { selectedPort = p },
                            text = p.toString(),
                        )
                    }
                }
            }
        },
        confirmButton = {
            PFilledButton(
                text = stringResource(Res.string.save),
                buttonSize = ButtonSize.MEDIUM,
                onClick = {
                    val valid = editHostname.isNotBlank() && editHostname.endsWith(".local")
                    if (!valid) {
                        hostnameError = true
                        return@PFilledButton
                    }
                    onSave(editHostname, selectedPort)
                },
            )
        },
        dismissButton = {
            PTextButton(text = stringResource(Res.string.cancel), onClick = onDismiss)
        },
    )
}

@Composable
fun PortSelectionDialog(
    isHttps: Boolean,
    currentPort: Int,
    onDismiss: () -> Unit,
    onSelect: (Int) -> Unit,
) {
    val ports = if (isHttps) httpsPorts else httpPorts
    val isCustomPort = currentPort !in ports
    var selectedPort by remember { mutableIntStateOf(if (isCustomPort) -1 else currentPort) }
    var customPortText by remember { mutableStateOf(if (isCustomPort) currentPort.toString() else "") }
    var portError by remember { mutableStateOf(false) }

    AlertDialog(
        modifier = Modifier.fillMaxWidth(),
        containerColor = MaterialTheme.colorScheme.dialogSheetBackground,
        onDismissRequest = onDismiss,
        title = { Text(text = stringResource(Res.string.change_port)) },
        text = {
            Column {
                LazyColumn(
                    modifier = Modifier
                        .height(280.dp)
                        .selectableGroup(),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    items(ports.toList()) { p ->
                        PDialogRadioRow(
                            selected = p == selectedPort,
                            onClick = {
                                selectedPort = p
                                portError = false
                            },
                            text = p.toString(),
                        )
                    }
                    item {
                        PDialogRadioRow(
                            selected = selectedPort == -1,
                            onClick = {
                                selectedPort = -1
                                portError = false
                            },
                            text = stringResource(Res.string.custom_port),
                        )
                    }
                }
                if (selectedPort == -1) {
                    Spacer(modifier = Modifier.height(16.dp))
                    PTextField(
                        readOnly = false,
                        value = customPortText,
                        singleLine = true,
                        onValueChange = {
                            customPortText = it.filter { ch -> ch.isDigit() }
                            portError = false
                        },
                        placeholder = "1024-65535",
                        errorMessage = if (portError) stringResource(Res.string.invalid_port) else "",
                    )
                }
            }
        },
        confirmButton = {
            PFilledButton(
                text = stringResource(Res.string.save),
                buttonSize = ButtonSize.MEDIUM,
                onClick = {
                    if (selectedPort == -1) {
                        val port = customPortText.toIntOrNull()
                        if (port == null || port !in 1..65535) {
                            portError = true
                            return@PFilledButton
                        }
                        onSelect(port)
                    } else {
                        onSelect(selectedPort)
                    }
                    onDismiss()
                },
            )
        },
        dismissButton = {
            PTextButton(text = stringResource(Res.string.cancel), onClick = onDismiss)
        },
    )
}
