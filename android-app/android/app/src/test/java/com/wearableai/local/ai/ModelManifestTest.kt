package com.wearableai.local.ai

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files

class ModelManifestTest {
    @Test
    fun reportsMissingRequiredFiles() {
        val manifest = ModelManifest.parse(validManifest())
        val directory = Files.createTempDirectory("models").toFile()
        directory.resolve("whisper").mkdirs()
        directory.resolve("whisper/w.bin").writeBytes(byteArrayOf(1))

        assertEquals(listOf("llama"), manifest.missing(directory, setOf("whisper", "llama")))
    }

    @Test
    fun rejectsMalformedManifest() {
        val result = runCatching { ModelManifest.parse("""{"version":1}""") }
        assertTrue(result.isFailure)
    }

    @Test
    fun rejectsModelPathTraversal() {
        val result = runCatching {
            ModelManifest.parse(
                validManifest().replace("whisper/w.bin", "../outside.bin")
            )
        }
        assertTrue(result.isFailure)
    }

    @Test
    fun rejectsExtraModelArtifact() {
        val result = runCatching {
            ModelManifest.parse(
                validManifest().replace(
                    """"tokenizer":""",
                    """"unexpected":{"file":"minilm/extra.bin","sha256":"${"0".repeat(64)}","size":1},"tokenizer":"""
                )
            )
        }
        assertTrue(result.isFailure)
    }

    private fun validManifest(): String = """
        {
          "version": 2,
          "models": {
            "whisper": {"file":"whisper/w.bin","sha256":"${"0".repeat(64)}","size":1},
            "llama": {"file":"llama/l.gguf","sha256":"${"1".repeat(64)}","size":1},
            "minilm": {"file":"minilm/model.onnx","sha256":"${"2".repeat(64)}","size":1},
            "tokenizer": {"file":"minilm/vocab.txt","sha256":"${"3".repeat(64)}","size":1}
          }
        }
    """.trimIndent()
}
