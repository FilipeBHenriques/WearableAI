package com.wearableai.local.ai

import android.content.Context
import com.wearableai.local.BuildConfig
import java.io.File
import java.security.MessageDigest

class ModelStore(private val context: Context) {
    private val installedDirectory = File(context.filesDir, "models")
    private var activeDirectory = installedDirectory
    private val verifiedFiles = mutableSetOf<String>()
    var availabilityError: String? = null
        private set

    fun install(): ModelManifest {
        if (BuildConfig.DEBUG) {
            availabilityError = "Production AI models are intentionally omitted from debug builds."
            return ModelManifest.unavailable()
        }
        return runCatching {
            when (BuildConfig.MODEL_DELIVERY) {
                // Install-time asset packs are exposed through the application's AssetManager.
                "asset-pack" -> installBundledAssets()
                "bundled" -> installBundledAssets()
                else -> error("This build does not define a model delivery path.")
            }
        }.onFailure {
            availabilityError = it.message ?: "Production AI models are unavailable."
        }.getOrElse { ModelManifest.unavailable() }
    }

    fun validate(manifest: ModelManifest, required: Set<String>): List<String> {
        val errors = manifest.missing(activeDirectory, required).toMutableList()
        required.forEach { key ->
            val spec = manifest.models[key] ?: return@forEach
            val file = File(activeDirectory, spec.file)
            if (!file.isFile) {
                verifiedFiles.remove(spec.file)
            } else if (file.length() != spec.size) {
                verifiedFiles.remove(spec.file)
                errors += "$key:size"
            } else if (spec.file !in verifiedFiles) {
                if (sha256(file) != spec.sha256) {
                    errors += "$key:checksum"
                } else {
                    verifiedFiles += spec.file
                }
            }
        }
        return errors
    }

    fun path(manifest: ModelManifest, key: String): String? =
        manifest.models[key]?.file?.let { File(activeDirectory, it) }?.takeIf(File::isFile)?.absolutePath

    private fun installBundledAssets(): ModelManifest {
        val text = context.assets.open("models/model-manifest.json")
            .bufferedReader()
            .use { it.readText() }
        val manifest = ModelManifest.parse(text)
        installedDirectory.mkdirs()
        activeDirectory = installedDirectory
        manifest.models.values.forEach { spec ->
            val destination = File(installedDirectory, spec.file)
            val valid = destination.isFile &&
                destination.length() == spec.size &&
                sha256(destination) == spec.sha256
            if (!valid) {
                verifiedFiles.remove(spec.file)
                destination.parentFile?.mkdirs()
                val temporary = File(destination.parentFile, "${destination.name}.part")
                temporary.delete()
                try {
                    context.assets.open("models/${spec.file}").use { input ->
                        temporary.outputStream().use(input::copyTo)
                    }
                    check(temporary.length() == spec.size) {
                        "Bundled model ${spec.file} has the wrong size."
                    }
                    check(sha256(temporary) == spec.sha256) {
                        "Bundled model ${spec.file} failed checksum verification."
                    }
                    destination.delete()
                    check(temporary.renameTo(destination)) {
                        "Could not install model ${spec.file}."
                    }
                } catch (error: Throwable) {
                    temporary.delete()
                    throw error
                }
            }
            verifiedFiles += spec.file
        }
        availabilityError = null
        return manifest
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

}
