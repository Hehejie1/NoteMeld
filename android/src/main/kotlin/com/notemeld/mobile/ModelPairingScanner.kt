package com.notemeld.mobile

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.notemeld.ui.NoteMeldBottomSheet
import com.notemeld.ui.NoteMeldSecondaryButton
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

internal fun parseNoteMeldPairingCode(raw: String): String? = runCatching {
    val uri = java.net.URI(raw.trim())
    if (uri.scheme != "notemeld" || uri.host != "pair") return@runCatching null
    val fields = uri.rawQuery?.split('&')?.mapNotNull { item ->
        val parts = item.split('=', limit = 2)
        if (parts.size != 2) null else java.net.URLDecoder.decode(parts[0], "UTF-8") to java.net.URLDecoder.decode(parts[1], "UTF-8")
    } ?: return@runCatching null
    if (fields.size != 1 || fields.single().first != "code") return@runCatching null
    fields.single().second.takeIf { it.matches(Regex("^[A-Za-z0-9_-]{8,128}$")) }
}.getOrNull()

/** 扫码结果分类：配对码与模型配置分享互斥，两者都不是即为不支持。 */
internal sealed interface ScanTarget {
    data class PairCode(val code: String) : ScanTarget
    data class ModelShare(val raw: String, val decoded: ModelSharePayload.DecodedShare) : ScanTarget
}

internal fun classifyScanResult(raw: String): ScanTarget? {
    val trimmed = raw.trim()
    val pairCode = parseNoteMeldPairingCode(trimmed)
    if (pairCode != null) return ScanTarget.PairCode(pairCode)
    // pair URI 形态正确但 code 非法时，不得再回落到 model-add 判定。
    val isPairUri = runCatching {
        val uri = java.net.URI(trimmed)
        uri.scheme == "notemeld" && uri.host == "pair"
    }.getOrDefault(false)
    if (isPairUri) return null
    // decodeShare 对一切畸形输入本就返回 null；外层再兜底，保证解析异常不逃逸到调用方。
    val decoded = runCatching { ModelSharePayload.decodeShare(trimmed) }.getOrNull() ?: return null
    return ScanTarget.ModelShare(trimmed, decoded)
}

@Composable
fun ModelPairingScannerSheet(
    language: String,
    onDismiss: () -> Unit,
    onPairingCode: (String, (Result<List<String>>) -> Unit) -> Unit,
    onModelShare: (ModelSharePayload.DecodedShare) -> Unit,
) {
    fun t(key: String): String = mobileText(language, key)
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    var permissionGranted by remember { mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) }
    var status by remember { mutableStateOf(t("scannerIntro")) }
    var pairing by remember { mutableStateOf(false) }
    val handled = remember { AtomicBoolean(false) }
    val cameraExecutor = remember { Executors.newSingleThreadExecutor() }
    val barcodeScanner = remember { BarcodeScanning.getClient(BarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build()) }
    var cameraProvider by remember { mutableStateOf<ProcessCameraProvider?>(null) }
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        permissionGranted = granted
        status = if (granted) t("scannerAlign") else t("scannerDenied")
    }
    LaunchedEffect(Unit) { if (!permissionGranted) permissionLauncher.launch(Manifest.permission.CAMERA) }
    DisposableEffect(Unit) { onDispose { cameraProvider?.unbindAll(); barcodeScanner.close(); cameraExecutor.shutdown() } }

    NoteMeldBottomSheet(t("scan"), onDismiss, eyebrow = t("scanPairing"), testTag = "notemeld-model-scan-sheet") {
        if (permissionGranted) {
            AndroidView(
                factory = { viewContext ->
                    PreviewView(viewContext).also { previewView ->
                        previewView.scaleType = PreviewView.ScaleType.FILL_CENTER
                        val providerFuture = ProcessCameraProvider.getInstance(viewContext)
                        providerFuture.addListener({
                            val provider = providerFuture.get()
                            cameraProvider = provider
                            val preview = Preview.Builder().build().also { it.surfaceProvider = previewView.surfaceProvider }
                            val analysis = ImageAnalysis.Builder().setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST).build()
                            analysis.setAnalyzer(cameraExecutor, object : ImageAnalysis.Analyzer {
                                @ExperimentalGetImage
                                override fun analyze(proxy: ImageProxy) {
                                    val mediaImage = proxy.image
                                    if (mediaImage == null || handled.get() || pairing) { proxy.close(); return }
                                    val image = InputImage.fromMediaImage(mediaImage, proxy.imageInfo.rotationDegrees)
                                    barcodeScanner.process(image)
                                        .addOnSuccessListener { codes ->
                                            val raw = codes.firstNotNullOfOrNull { it.rawValue }
                                            val target = raw?.let(::classifyScanResult)
                                            if (raw != null && target == null) status = t("scannerNotSupported")
                                            when (target) {
                                                is ScanTarget.PairCode -> if (handled.compareAndSet(false, true)) {
                                                    pairing = true
                                                    status = t("scannerPairing")
                                                    onPairingCode(target.code) { result ->
                                                        pairing = false
                                                        result.onSuccess { names -> status = t("scannerPairOk").format(names.size) }
                                                            .onFailure { error -> handled.set(false); status = error.message ?: t("scannerPairFail") }
                                                    }
                                                }
                                                is ScanTarget.ModelShare -> if (handled.compareAndSet(false, true)) {
                                                    status = t("scannerShareOk")
                                                    onModelShare(target.decoded)
                                                }
                                                null -> Unit
                                            }
                                        }
                                        .addOnFailureListener { status = t("scannerNotSupported") }
                                        .addOnCompleteListener { proxy.close() }
                                }
                            })
                            runCatching { provider.unbindAll(); provider.bindToLifecycle(lifecycleOwner, CameraSelector.DEFAULT_BACK_CAMERA, preview, analysis) }
                                .onFailure { status = t("scannerCameraFail") }
                        }, ContextCompat.getMainExecutor(viewContext))
                    }
                },
                modifier = Modifier.fillMaxWidth().height(260.dp).clip(RoundedCornerShape(14.dp)),
            )
        } else {
            Box(Modifier.fillMaxWidth().height(160.dp).padding(20.dp)) { Text(status, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            NoteMeldSecondaryButton(t("allowCamera"), { permissionLauncher.launch(Manifest.permission.CAMERA) }, modifier = Modifier.fillMaxWidth())
        }
        Text(status, color = if (pairing) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
    }
}
