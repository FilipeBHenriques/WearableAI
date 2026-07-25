package com.wearableai.local

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.getcapacitor.annotation.CapacitorPlugin
import com.wearableai.local.ai.LocalAIPlugin
import com.wearableai.local.audio.LocalAudioPlugin
import com.wearableai.local.location.LocalLocationPlugin
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class PluginRegistrationTest {
    @Test
    fun nativePluginsExposeStableBridgeNames() {
        assertEquals("LocalAudio", pluginName(LocalAudioPlugin::class.java))
        assertEquals("LocalAI", pluginName(LocalAIPlugin::class.java))
        assertEquals("LocalLocation", pluginName(LocalLocationPlugin::class.java))
    }

    private fun pluginName(type: Class<*>): String =
        type.getAnnotation(CapacitorPlugin::class.java)?.name
            ?: error("${type.simpleName} has no CapacitorPlugin annotation.")
}
