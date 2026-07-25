package com.wearableai.local.audio

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder

class WavHeaderTest {
    @Test
    fun writesCanonicalPcm16MonoHeader() {
        val header = WavHeader.pcm16Mono(dataBytes = 32_000)
        val littleEndian = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)

        assertEquals(44, header.size)
        assertArrayEquals("RIFF".toByteArray(), header.copyOfRange(0, 4))
        assertArrayEquals("WAVE".toByteArray(), header.copyOfRange(8, 12))
        assertEquals(32_036, littleEndian.getInt(4))
        assertEquals(1, littleEndian.getShort(22).toInt())
        assertEquals(16_000, littleEndian.getInt(24))
        assertEquals(32_000, littleEndian.getInt(28))
        assertEquals(16, littleEndian.getShort(34).toInt())
        assertEquals(32_000, littleEndian.getInt(40))
    }
}
