package com.wearableai.local.ai

import org.json.JSONObject
import java.io.File

data class ModelSpec(val file: String, val sha256: String, val size: Long)

data class ModelManifest(val version: Int, val models: Map<String, ModelSpec>) {
    fun missing(baseDir: File, required: Set<String>): List<String> =
        required.filter { key ->
            val relative = models[key]?.file
            relative.isNullOrBlank() || !File(baseDir, relative).isFile
        }

    companion object {
        fun parse(json: String): ModelManifest {
            val root = JSONObject(json)
            require(root.getInt("version") == CURRENT_VERSION) { "Unsupported model manifest version." }
            val entries = root.getJSONObject("models")
            val keys = buildSet {
                val iterator = entries.keys()
                while (iterator.hasNext()) add(iterator.next())
            }
            require(keys == REQUIRED_ARTIFACTS) {
                "Model manifest must contain exactly the production artifacts."
            }
            val models = buildMap {
                keys.forEach { key ->
                    val value = entries.getJSONObject(key)
                    val file = value.getString("file")
                    val parts = file.split('/')
                    require(
                        file.isNotBlank() &&
                            '\\' !in file &&
                            ':' !in file &&
                            !file.startsWith("/") &&
                            parts.none { it.isBlank() || it == "." || it == ".." }
                    ) { "Unsafe model path for $key." }
                    val sha256 = value.getString("sha256").lowercase()
                    require(sha256.matches(Regex("[0-9a-f]{64}"))) {
                        "Invalid SHA-256 for $key."
                    }
                    val size = value.getLong("size")
                    require(size > 0) { "Invalid model size for $key." }
                    put(
                        key,
                        ModelSpec(file, sha256, size)
                    )
                }
            }
            require(models.map { it.value.file.substringBefore('/') }.toSet() == MODEL_DIRECTORIES) {
                "Model manifest must use exactly three model directories."
            }
            return ModelManifest(CURRENT_VERSION, models)
        }

        fun unavailable(): ModelManifest = ModelManifest(CURRENT_VERSION, emptyMap())

        private const val CURRENT_VERSION = 2
        private val REQUIRED_ARTIFACTS = setOf("whisper", "llama", "minilm", "tokenizer")
        private val MODEL_DIRECTORIES = setOf("whisper", "llama", "minilm")
    }
}
