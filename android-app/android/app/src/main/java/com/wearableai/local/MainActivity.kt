package com.wearableai.local

import android.os.Bundle
import com.getcapacitor.BridgeActivity
import com.wearableai.local.ai.LocalAIPlugin
import com.wearableai.local.audio.LocalAudioPlugin
import com.wearableai.local.location.LocalLocationPlugin

class MainActivity : BridgeActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        registerPlugin(LocalAudioPlugin::class.java)
        registerPlugin(LocalAIPlugin::class.java)
        registerPlugin(LocalLocationPlugin::class.java)
        super.onCreate(savedInstanceState)
    }
}
