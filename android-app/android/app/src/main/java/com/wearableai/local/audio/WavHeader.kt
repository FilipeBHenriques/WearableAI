package com.wearableai.local.audio

import java.nio.ByteBuffer
import java.nio.ByteOrder

object WavHeader {
    const val SIZE = 44

    fun pcm16Mono(dataBytes: Long, sampleRate: Int = 16_000): ByteArray {
        require(dataBytes in 0..0xffff_ffffL) { "PCM payload is too large for WAV." }
        return ByteBuffer.allocate(SIZE).order(ByteOrder.LITTLE_ENDIAN).apply {
            put("RIFF".toByteArray(Charsets.US_ASCII))
            putInt((36L + dataBytes).toInt())
            put("WAVEfmt ".toByteArray(Charsets.US_ASCII))
            putInt(16)
            putShort(1)
            putShort(1)
            putInt(sampleRate)
            putInt(sampleRate * 2)
            putShort(2)
            putShort(16)
            put("data".toByteArray(Charsets.US_ASCII))
            putInt(dataBytes.toInt())
        }.array()
    }
}
