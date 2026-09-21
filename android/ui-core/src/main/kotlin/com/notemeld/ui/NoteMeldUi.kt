package com.notemeld.ui

import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.ui.draw.clip
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Snackbar
import androidx.compose.material3.Surface
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.Typography
import androidx.compose.material3.Shapes
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay

/** Semantic tokens shared by the mobile surfaces; business state stays outside ui-core. */
object NoteMeldTokens {
    val spacingXs = 4.dp
    val spacingSm = 8.dp
    val spacingMd = 12.dp
    val spacingLg = 20.dp
    val cornerMd = 12.dp
    val focusRing = Color(0xff2f6fed)
    val offline = Color(0xffb5474d)
    val background = Color(0xfff7f8fb)
    val surfaceMuted = Color(0xfff1f3f8)
    val border = Color(0xffdfe4ec)
    val mutedText = Color(0xff7d879a)
}

@Composable
fun NoteMeldTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (darkTheme) {
        androidx.compose.material3.darkColorScheme(
            primary = Color(0xff9bb7ff),
            onPrimary = Color(0xff10234f),
            secondary = Color(0xffb8c4dd),
            background = Color(0xff111318),
            surface = Color(0xff1a1d24),
            error = Color(0xffffb4ab),
        )
    } else {
        androidx.compose.material3.lightColorScheme(
            primary = Color(0xff315eea),
            onPrimary = Color.White,
            secondary = Color(0xff53647d),
            background = Color(0xfff7f8fb),
            surface = Color.White,
            error = Color(0xffb5474d),
        )
    }
    val typography = Typography().run {
        copy(
            bodyLarge = bodyLarge.copy(fontSize = 16.sp, lineHeight = 24.sp),
            bodyMedium = bodyMedium.copy(fontSize = 14.sp, lineHeight = 21.sp),
            bodySmall = bodySmall.copy(fontSize = 12.sp, lineHeight = 18.sp),
            titleLarge = titleLarge.copy(fontSize = 22.sp, lineHeight = 28.sp),
            titleMedium = titleMedium.copy(fontSize = 16.sp, lineHeight = 24.sp),
            headlineMedium = headlineMedium.copy(fontSize = 28.sp, lineHeight = 34.sp),
            labelMedium = labelMedium.copy(fontSize = 12.sp, lineHeight = 16.sp),
        )
    }
    MaterialTheme(
        colorScheme = colors,
        typography = typography,
        shapes = Shapes(
            extraSmall = androidx.compose.foundation.shape.RoundedCornerShape(7.dp),
            small = androidx.compose.foundation.shape.RoundedCornerShape(9.dp),
            medium = androidx.compose.foundation.shape.RoundedCornerShape(12.dp),
            large = androidx.compose.foundation.shape.RoundedCornerShape(14.dp),
        ),
        content = content,
    )
}

@Composable
fun NoteMeldEmptyState(
    title: String,
    description: String? = null,
    modifier: Modifier = Modifier,
    testTag: String = "notemeld-empty-state",
) {
    Card(
        modifier = modifier.fillMaxWidth().testTag(testTag).semantics { this.contentDescription = title },
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(NoteMeldTokens.spacingLg),
            verticalArrangement = Arrangement.spacedBy(NoteMeldTokens.spacingSm),
        ) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            description?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}

@Composable
fun NoteMeldOfflineState(
    message: String = "网络离线：仅可查看已同步内容",
    modifier: Modifier = Modifier,
    testTag: String = "notemeld-offline-state",
) {
    Text(message, color = NoteMeldTokens.offline, style = MaterialTheme.typography.labelSmall, modifier = modifier.testTag(testTag).semantics { this.contentDescription = message })
}

@Composable
fun NoteMeldLoadingState(
    title: String = "正在加载…",
    modifier: Modifier = Modifier,
    testTag: String = "notemeld-loading-state",
) {
    Card(modifier = modifier.fillMaxWidth().testTag(testTag).semantics { this.contentDescription = title }) {
        Row(Modifier.fillMaxWidth().padding(NoteMeldTokens.spacingLg), horizontalArrangement = Arrangement.spacedBy(NoteMeldTokens.spacingSm), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            CircularProgressIndicator()
            Text(title, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
fun NoteMeldErrorState(
    title: String = "加载失败",
    description: String? = null,
    onRetry: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
    testTag: String = "notemeld-error-state",
) {
    Card(modifier = modifier.fillMaxWidth().testTag(testTag).semantics { this.contentDescription = title }) {
        Column(Modifier.fillMaxWidth().padding(NoteMeldTokens.spacingLg), verticalArrangement = Arrangement.spacedBy(NoteMeldTokens.spacingSm)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.error)
            description?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
            onRetry?.let { NoteMeldSecondaryButton("重试", it, contentDescription = "重试") }
        }
    }
}

@Composable
fun NoteMeldProgress(progress: Float, modifier: Modifier = Modifier, testTag: String = "notemeld-progress") {
    androidx.compose.material3.LinearProgressIndicator(progress = { progress.coerceIn(0f, 1f) }, modifier = modifier.fillMaxWidth().testTag(testTag))
}

@Composable
fun NoteMeldSnackbar(message: String, modifier: Modifier = Modifier, actionLabel: String? = null, onAction: (() -> Unit)? = null) {
    Snackbar(modifier = modifier.testTag("notemeld-snackbar"), action = if (actionLabel != null && onAction != null) ({ TextButton(onClick = onAction) { Text(actionLabel) } }) else null) { Text(message) }
}

@Composable
fun NoteMeldToast(message: String, onDismiss: () -> Unit, modifier: Modifier = Modifier, durationMs: Long = 3000L) {
    LaunchedEffect(message, durationMs) { delay(durationMs); onDismiss() }
    Surface(
        modifier = modifier.testTag("notemeld-toast").semantics { contentDescription = message },
        shape = androidx.compose.foundation.shape.RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 4.dp,
        shadowElevation = 8.dp,
        border = androidx.compose.foundation.BorderStroke(1.dp, NoteMeldTokens.border),
    ) {
        Row(Modifier.padding(start = 16.dp, end = 6.dp, top = 10.dp, bottom = 10.dp), verticalAlignment = androidx.compose.ui.Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(message, modifier = Modifier.weight(1f), color = MaterialTheme.colorScheme.onSurface)
            TextButton(onClick = onDismiss, modifier = Modifier.semantics { contentDescription = "关闭提示" }, contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 8.dp)) { Text("×", fontSize = 22.sp) }
        }
    }
}

@Composable
fun NoteMeldField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    singleLine: Boolean = true,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    placeholder: String? = null,
    testTag: String = "notemeld-field",
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        enabled = enabled,
        singleLine = singleLine,
        visualTransformation = visualTransformation,
        label = { Text(label) },
        placeholder = { placeholder?.let { Text(it) } },
        modifier = modifier.fillMaxWidth().testTag(testTag),
    )
}

@Composable
fun NoteMeldSwitchRow(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    modifier: Modifier = Modifier,
) {
    androidx.compose.foundation.layout.Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = androidx.compose.foundation.layout.Arrangement.SpaceBetween,
        verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
    ) {
        Text(label)
        Switch(checked = checked, onCheckedChange = onCheckedChange)
    }
}

/** Shared, business-model-free primitives consumed by the Android product screens. */
@Composable
fun NoteMeldPrimaryButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    contentDescription: String = label,
    testTag: String = "notemeld-primary-button",
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.testTag(testTag).semantics { this.contentDescription = contentDescription },
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
    ) { Text(label) }
}

@Composable
fun NoteMeldSecondaryButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    contentDescription: String = label,
    testTag: String = "notemeld-secondary-button",
) {
    OutlinedButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.testTag(testTag).semantics { this.contentDescription = contentDescription },
    ) { Text(label) }
}

@Composable
fun NoteMeldButtonRow(content: @Composable RowScope.() -> Unit) {
    androidx.compose.foundation.layout.Row(content = content)
}

/** Compact segmented control shared by work-mode and preference selectors. */
@Composable
fun NoteMeldSegmentedControl(
    options: List<String>,
    selectedIndex: Int,
    onSelected: (Int) -> Unit,
    modifier: Modifier = Modifier,
    contentDescriptionPrefix: String = "选项",
) {
    Row(
        modifier = modifier.fillMaxWidth().height(40.dp).clip(androidx.compose.foundation.shape.RoundedCornerShape(11.dp)).background(MaterialTheme.colorScheme.surfaceVariant).padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        options.forEachIndexed { index, option ->
            Box(
                modifier = Modifier.weight(1f).fillMaxHeight()
                    .clip(androidx.compose.foundation.shape.RoundedCornerShape(8.dp))
                    .background(if (index == selectedIndex) MaterialTheme.colorScheme.surface else Color.Transparent)
                    .clickable { onSelected(index) }
                    .semantics { this.contentDescription = "$contentDescriptionPrefix-$option" },
                contentAlignment = androidx.compose.ui.Alignment.Center,
            ) {
                Text(option, style = MaterialTheme.typography.labelSmall, color = if (index == selectedIndex) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/** Product-level action primitive so screens do not fork Material button behavior. */
@Composable
fun NoteMeldActionButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    content: @Composable RowScope.() -> Unit,
) {
    Button(onClick = onClick, enabled = enabled, modifier = modifier, content = content)
}

/** Product-level low-emphasis action primitive used by menus and inline actions. */
@Composable
fun NoteMeldTextButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    content: @Composable RowScope.() -> Unit,
) {
    TextButton(onClick = onClick, enabled = enabled, modifier = modifier, content = content)
}

/** Icon-only action with a mandatory accessible name. The icon remains owned by the product. */
@Composable
fun NoteMeldIconButton(
    contentDescription: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    testTag: String = "notemeld-icon-button",
    icon: @Composable () -> Unit,
) {
    IconButton(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.size(48.dp).testTag(testTag).semantics { this.contentDescription = contentDescription },
    ) { icon() }
}

/** Product-neutral app bar. Page navigation and actions are injected by the caller. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NoteMeldAppBar(
    title: String,
    modifier: Modifier = Modifier,
    onNavigateBack: (() -> Unit)? = null,
    navigationContentDescription: String = "返回",
    actions: @Composable RowScope.() -> Unit = {},
) {
    TopAppBar(
        title = { Text(title) },
        modifier = modifier.testTag("notemeld-app-bar"),
        navigationIcon = {
            if (onNavigateBack != null) {
                TextButton(
                    onClick = onNavigateBack,
                    modifier = Modifier.semantics { this.contentDescription = navigationContentDescription },
                ) { Text("返回") }
            }
        },
        actions = actions,
        colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.background),
    )
}

/** Confirmation dialog with stable semantics for destructive and irreversible actions. */
@Composable
fun NoteMeldConfirmDialog(
    title: String,
    message: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    confirmLabel: String = "确认",
    dismissLabel: String = "取消",
    testTag: String = "notemeld-confirm-dialog",
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = Modifier.testTag(testTag),
        title = { Text(title) },
        text = { Text(message) },
        confirmButton = { NoteMeldPrimaryButton(confirmLabel, onConfirm, testTag = "notemeld-dialog-confirm") },
        dismissButton = { NoteMeldSecondaryButton(dismissLabel, onDismiss, testTag = "notemeld-dialog-dismiss") },
    )
}

/** Bottom-sheet listbox primitive. Dismissal never changes the selected value by itself. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NoteMeldChoiceSheet(
    title: String,
    options: List<String>,
    selected: String?,
    onOptionSelected: (String) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
    testTag: String = "notemeld-choice-sheet",
) {
    NoteMeldBottomSheet(title = title, onDismiss = onDismiss, modifier = modifier, testTag = testTag) {
        options.forEach { option ->
            val optionTag = "notemeld-choice-${option.hashCode()}"
            NoteMeldTextButton(
                onClick = { onOptionSelected(option) },
                modifier = Modifier.fillMaxWidth().height(48.dp).testTag(optionTag),
            ) { Text(option, color = if (option == selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface) }
        }
    }
}

/** Shared NoteMeld bottom-sheet shell. Page-specific content belongs inside the slot. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NoteMeldBottomSheet(
    title: String,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
    eyebrow: String? = null,
    testTag: String = "notemeld-bottom-sheet",
    content: @Composable ColumnScope.() -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        modifier = modifier.testTag(testTag),
        shape = androidx.compose.foundation.shape.RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp),
        containerColor = MaterialTheme.colorScheme.surface,
        tonalElevation = 0.dp,
        dragHandle = { androidx.compose.material3.BottomSheetDefaults.DragHandle(color = NoteMeldTokens.border) },
    ) {
        Column(
            Modifier.fillMaxWidth().padding(start = 20.dp, end = 20.dp, bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(NoteMeldTokens.spacingSm),
            content = {
                Row(Modifier.fillMaxWidth(), verticalAlignment = androidx.compose.ui.Alignment.Top, horizontalArrangement = Arrangement.SpaceBetween) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        eyebrow?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.labelMedium) }
                        Text(title, style = MaterialTheme.typography.headlineSmall)
                    }
                    NoteMeldTextButton(onClick = onDismiss, modifier = Modifier.semantics { contentDescription = "关闭弹窗" }) { Text("关闭") }
                }
                content()
            },
        )
    }
}

@Composable
fun NoteMeldBadge(
    text: String,
    modifier: Modifier = Modifier,
    testTag: String = "notemeld-badge",
) {
    OutlinedCard(modifier = modifier.testTag(testTag)) {
        Text(text, modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp), style = MaterialTheme.typography.labelMedium)
    }
}

@Composable
fun NoteMeldSkeleton(
    modifier: Modifier = Modifier,
    testTag: String = "notemeld-skeleton",
) {
    Box(
        modifier = modifier.fillMaxWidth().size(height = 48.dp, width = 1.dp)
            .testTag(testTag)
            .semantics { this.contentDescription = "正在加载" },
    )
}
