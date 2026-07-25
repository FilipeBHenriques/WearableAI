package com.wearableai.local.ai

import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.wearableai.local.BuildConfig
import java.io.File
import java.util.concurrent.Executors

@CapacitorPlugin(name = "LocalAI")
class LocalAIPlugin : Plugin() {
    private val executor = Executors.newSingleThreadExecutor()
    private lateinit var store: ModelStore
    @Volatile private var manifest: ModelManifest? = null
    @Volatile private var embedder: MiniLmEmbedder? = null
    @Volatile private var lastError: String? = null

    override fun load() {
        store = ModelStore(context)
    }

    @PluginMethod
    fun warmup(call: PluginCall) = onWorker(call) {
        val current = store.install().also { manifest = it }
        val required = if (BuildConfig.REQUIRE_PRODUCTION_MODELS) REQUIRED_MODELS else emptySet()
        val validation = store.validate(current, required)
        if (validation.isNotEmpty()) {
            throw AiException("MODEL_MISSING", "Required model assets are unavailable: ${validation.joinToString()}")
        }
        initializeEmbedder(current)
        val native = if (NativeInference.loaded) {
            NativeInference.nativeWarmup(store.path(current, "whisper"), store.path(current, "llama"))
        } else {
            """{"loaded":false,"error":${JSONObjectQuote.quote(NativeInference.loadError)}}"""
        }
        statusObject(current).put("native", native)
    }

    @PluginMethod
    fun status(call: PluginCall) = onWorker(call) {
        val current = manifest ?: store.install().also { manifest = it }
        statusObject(current)
    }

    @PluginMethod
    fun transcribe(call: PluginCall) = onWorker(call) {
        val wavPath = call.getString("path") ?: throw AiException("INVALID_INPUT", "A WAV path is required.")
        if (!File(wavPath).isFile) throw AiException("AUDIO_MISSING", "The WAV input does not exist.")
        val current = currentManifest()
        val model = store.path(current, "whisper")
            ?: throw AiException("MODEL_MISSING", "The whisper model is not installed.")
        requireNative()
        JSObject().put("text", NativeInference.nativeTranscribe(wavPath, model))
    }

    @PluginMethod
    fun generate(call: PluginCall) = onWorker(call) {
        val prompt = call.getString("prompt")?.takeIf(String::isNotBlank)
            ?: throw AiException("INVALID_INPUT", "A non-empty prompt is required.")
        val current = currentManifest()
        val model = store.path(current, "llama")
            ?: throw AiException("MODEL_MISSING", "The llama model is not installed.")
        requireNative()
        val maxTokens = (call.getInt("maxTokens") ?: 256).coerceIn(1, 2048)
        JSObject().put("text", NativeInference.nativeGenerate(prompt, model, maxTokens))
    }

    @PluginMethod
    fun embed(call: PluginCall) = onWorker(call) {
        val texts = call.getArray("texts") ?: throw AiException("INVALID_INPUT", "texts must be an array.")
        if (texts.length() > 128) throw AiException("INVALID_INPUT", "At most 128 texts may be embedded.")
        val current = currentManifest()
        initializeEmbedder(current)
        val engine = embedder ?: throw AiException("MODEL_MISSING", "MiniLM model or tokenizer is missing.")
        val vectors = JSArray()
        for (index in 0 until texts.length()) {
            val vector = JSArray()
            engine.embed(texts.getString(index)).forEach { vector.put(it.toDouble()) }
            vectors.put(vector)
        }
        JSObject().put("vectors", vectors)
    }

    private fun initializeEmbedder(current: ModelManifest) {
        if (embedder != null) return
        val model = store.path(current, "minilm") ?: return
        val tokenizer = store.path(current, "tokenizer") ?: return
        val vocabulary = File(tokenizer).readLines(Charsets.UTF_8)
        embedder = MiniLmEmbedder(model, vocabulary)
    }

    private fun currentManifest(): ModelManifest =
        manifest ?: store.install().also { manifest = it }

    private fun requireNative() {
        if (!NativeInference.loaded) {
            throw AiException("NATIVE_UNAVAILABLE", NativeInference.loadError ?: "Native inference is unavailable.")
        }
    }

    private fun statusObject(current: ModelManifest): JSObject {
        val missing = store.validate(current, REQUIRED_MODELS)
        return JSObject().apply {
            put("available", missing.isEmpty() && NativeInference.loaded)
            put("nativeLoaded", NativeInference.loaded)
            put("embeddingAvailable", store.path(current, "minilm") != null && store.path(current, "tokenizer") != null)
            put("missingModels", JSArray(missing))
            put("error", lastError ?: store.availabilityError ?: NativeInference.loadError)
            put("nativeStatus", if (NativeInference.loaded) NativeInference.nativeStatus() else null)
        }
    }

    private fun onWorker(call: PluginCall, action: () -> JSObject) {
        executor.execute {
            try {
                val result = action()
                lastError = null
                call.resolve(result)
            } catch (error: Throwable) {
                lastError = error.message
                val typed = error as? AiException
                call.reject(
                    error.message ?: "Local AI operation failed.",
                    typed?.code ?: "LOCAL_AI_FAILED",
                    error.asException()
                )
            }
        }
    }

    override fun handleOnDestroy() {
        executor.shutdownNow()
        embedder?.close()
        super.handleOnDestroy()
    }

    private class AiException(val code: String, message: String) : Exception(message)

    private object JSONObjectQuote {
        fun quote(value: String?): String = org.json.JSONObject.quote(value ?: "unknown")
    }

    companion object {
        private val REQUIRED_MODELS = setOf("whisper", "llama", "minilm", "tokenizer")
    }
}

private fun Throwable.asException(): Exception = this as? Exception ?: Exception(this)
