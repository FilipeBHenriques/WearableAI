package com.wearableai.local.ai

object NativeInference {
    val loaded: Boolean
    val loadError: String?

    init {
        var error: String? = null
        val success = try {
            System.loadLibrary("wearableai")
            true
        } catch (failure: Throwable) {
            error = failure.message ?: failure.javaClass.simpleName
            false
        }
        loaded = success
        loadError = error
    }

    external fun nativeStatus(): String
    external fun nativeWarmup(whisperModelPath: String?, llamaModelPath: String?): String
    external fun nativeTranscribe(wavPath: String, whisperModelPath: String): String
    external fun nativeGenerate(prompt: String, llamaModelPath: String, maxTokens: Int): String
}
