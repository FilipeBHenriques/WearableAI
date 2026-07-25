package com.wearableai.local.ai

import ai.onnxruntime.OnnxTensor
import ai.onnxruntime.OrtEnvironment
import ai.onnxruntime.OrtSession
import java.nio.LongBuffer
import kotlin.math.sqrt

class MiniLmEmbedder(modelPath: String, vocabulary: List<String>) : AutoCloseable {
    private val environment = OrtEnvironment.getEnvironment()
    private val session = OrtSession.SessionOptions().use { options ->
        environment.createSession(modelPath, options)
    }
    private val tokenizer = WordPieceTokenizer(vocabulary)

    fun embed(text: String): FloatArray {
        val tokenIds = tokenizer.encode(text)
        val shape = longArrayOf(1, tokenIds.size.toLong())
        val ids = tensor(tokenIds.map(Int::toLong).toLongArray(), shape)
        val mask = tensor(LongArray(tokenIds.size) { 1L }, shape)
        val types = tensor(LongArray(tokenIds.size), shape)
        val inputs = mutableMapOf<String, OnnxTensor>(
            "input_ids" to ids,
            "attention_mask" to mask
        )
        if ("token_type_ids" in session.inputNames) inputs["token_type_ids"] = types
        try {
            session.run(inputs).use { result ->
                @Suppress("UNCHECKED_CAST")
                val states = result[0].value as Array<Array<FloatArray>>
                val pooled = FloatArray(states[0][0].size)
                states[0].forEach { token ->
                    token.indices.forEach { dimension -> pooled[dimension] += token[dimension] }
                }
                var squared = 0.0
                pooled.indices.forEach { dimension ->
                    pooled[dimension] /= states[0].size.toFloat()
                    squared += pooled[dimension] * pooled[dimension]
                }
                val norm = sqrt(squared).toFloat().coerceAtLeast(1e-12f)
                pooled.indices.forEach { pooled[it] /= norm }
                return pooled
            }
        } finally {
            ids.close()
            mask.close()
            types.close()
        }
    }

    private fun tensor(values: LongArray, shape: LongArray): OnnxTensor =
        OnnxTensor.createTensor(environment, LongBuffer.wrap(values), shape)

    override fun close() {
        session.close()
    }
}
