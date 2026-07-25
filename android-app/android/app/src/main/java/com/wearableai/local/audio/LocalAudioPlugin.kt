package com.wearableai.local.audio

import android.Manifest
import android.content.Intent
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import androidx.core.content.ContextCompat
import com.getcapacitor.JSObject
import com.getcapacitor.PermissionState
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import com.getcapacitor.annotation.Permission
import com.getcapacitor.annotation.PermissionCallback
import java.io.File
import java.io.RandomAccessFile
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

@CapacitorPlugin(
    name = "LocalAudio",
    permissions = [Permission(alias = "microphone", strings = [Manifest.permission.RECORD_AUDIO])]
)
class LocalAudioPlugin : Plugin() {
    private val recording = AtomicBoolean(false)
    @Volatile private var recorder: AudioRecord? = null
    @Volatile private var worker: Thread? = null
    @Volatile private var output: File? = null
    @Volatile private var startedAt = 0L
    @Volatile private var failure: String? = null

    override fun load() {
        pruneTemporaryRecordings()
        recoverRetainedAudio()
    }

    @PluginMethod
    fun start(call: PluginCall) {
        if (getPermissionState("microphone") != PermissionState.GRANTED) {
            requestPermissionForAlias("microphone", call, "microphonePermissionCallback")
            return
        }
        startGranted(call)
    }

    @PermissionCallback
    private fun microphonePermissionCallback(call: PluginCall) {
        if (getPermissionState("microphone") == PermissionState.GRANTED) startGranted(call)
        else call.reject("Microphone permission is required.", "MICROPHONE_PERMISSION_DENIED")
    }

    private fun startGranted(call: PluginCall) {
        if (!recording.compareAndSet(false, true)) {
            call.reject("A recording is already active.", "RECORDING_ACTIVE")
            return
        }
        try {
            val min = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL, ENCODING)
            check(min > 0) { "16 kHz mono PCM recording is unsupported." }
            val audioRecord = AudioRecord(
                MediaRecorder.AudioSource.VOICE_RECOGNITION,
                SAMPLE_RATE, CHANNEL, ENCODING, maxOf(min * 2, 8192)
            )
            check(audioRecord.state == AudioRecord.STATE_INITIALIZED) { "AudioRecord initialization failed." }
            val dir = File(context.filesDir, "recordings").apply { mkdirs() }
            val file = File(dir, "capture-${System.currentTimeMillis()}.wav")
            RandomAccessFile(file, "rw").use { it.write(ByteArray(WavHeader.SIZE)) }
            output = file
            recorder = audioRecord
            failure = null
            startedAt = System.currentTimeMillis()
            ContextCompat.startForegroundService(context, Intent(context, AudioRecordingService::class.java))
            audioRecord.startRecording()
            worker = thread(name = "LocalAudioCapture") { writePcm(audioRecord, file, min) }
            call.resolve(statusObject())
        } catch (error: Throwable) {
            recording.set(false)
            recorder?.release()
            recorder = null
            output?.delete()
            output = null
            context.stopService(Intent(context, AudioRecordingService::class.java))
            call.reject(
                error.message ?: "Unable to start recording.",
                "AUDIO_START_FAILED",
                error as? Exception ?: Exception(error)
            )
        }
    }

    private fun writePcm(audioRecord: AudioRecord, file: File, bufferSize: Int) {
        val buffer = ByteArray(maxOf(bufferSize, 4096))
        try {
            RandomAccessFile(file, "rw").use { wav ->
                wav.seek(WavHeader.SIZE.toLong())
                var written = 0L
                while (recording.get()) {
                    val count = audioRecord.read(buffer, 0, buffer.size)
                    if (count > 0) {
                        check(written + count <= MAX_RECORDING_BYTES) {
                            "Maximum recording duration reached."
                        }
                        wav.write(buffer, 0, count)
                        written += count
                    }
                    else if (count < 0 && recording.get()) {
                        throw IllegalStateException("AudioRecord read failed: $count")
                    }
                }
            }
        } catch (error: Throwable) {
            failure = error.message ?: "Audio capture failed."
            recording.set(false)
        }
    }

    @PluginMethod
    fun stop(call: PluginCall) {
        if (!recording.getAndSet(false) && recorder == null) {
            call.reject("No recording is active.", "NO_RECORDING")
            return
        }
        val audioRecord = recorder
        try {
            if (audioRecord?.recordingState == AudioRecord.RECORDSTATE_RECORDING) audioRecord.stop()
            worker?.join(2_000)
            check(worker?.isAlive != true) { "Audio capture worker did not stop." }
            val file = output ?: error("Recording output is unavailable.")
            val dataBytes = (file.length() - WavHeader.SIZE).coerceAtLeast(0)
            RandomAccessFile(file, "rw").use {
                it.seek(0)
                it.write(WavHeader.pcm16Mono(dataBytes))
            }
            failure?.let { throw IllegalStateException(it) }
            call.resolve(JSObject().apply {
                put("path", file.absolutePath)
                put("uri", file.toURI().toString())
                put("mimeType", "audio/wav")
                put("sizeBytes", file.length())
                put("durationMs", dataBytes * 1000L / (SAMPLE_RATE * 2L))
            })
        } catch (error: Throwable) {
            output?.delete()
            call.reject(
                error.message ?: "Unable to finish recording.",
                "AUDIO_STOP_FAILED",
                error as? Exception ?: Exception(error)
            )
        } finally {
            audioRecord?.release()
            recorder = null
            worker = null
            output = null
            startedAt = 0L
            context.stopService(Intent(context, AudioRecordingService::class.java))
        }
    }

    @PluginMethod
    fun status(call: PluginCall) = call.resolve(statusObject())

    @PluginMethod
    fun retain(call: PluginCall) {
        try {
            val source = managedFile(call.getString("path") ?: error("A recording path is required."), "recordings")
            val noteId = call.getInt("noteId")?.takeIf { it > 0 } ?: error("A valid noteId is required.")
            check(source.isFile) { "The recording no longer exists." }
            val directory = File(context.filesDir, "note-audio").apply { mkdirs() }
            val destination = File(directory, "note-$noteId.wav")
            val temporary = File(directory, ".note-$noteId-${System.nanoTime()}.part")
            val backup = File(directory, ".note-$noteId.bak")
            try {
                source.inputStream().use { input ->
                    temporary.outputStream().use { output -> input.copyTo(output) }
                }
                check(temporary.length() == source.length()) { "Retained audio copy is incomplete." }
                backup.delete()
                if (destination.exists()) check(destination.renameTo(backup)) {
                    "Unable to stage existing note audio."
                }
                if (!temporary.renameTo(destination)) {
                    if (backup.exists()) backup.renameTo(destination)
                    error("Unable to install retained note audio.")
                }
                backup.delete()
                source.delete()
            } catch (error: Throwable) {
                temporary.delete()
                if (!destination.exists() && backup.exists()) backup.renameTo(destination)
                throw error
            }
            call.resolve(JSObject().apply {
                put("path", destination.absolutePath)
                put("uri", destination.toURI().toString())
            })
        } catch (error: Throwable) {
            call.reject(error.message ?: "Unable to retain recording.", "AUDIO_RETAIN_FAILED", error.asException())
        }
    }

    @PluginMethod
    fun delete(call: PluginCall) {
        try {
            val file = managedAudioFile(call.getString("path") ?: error("An audio path is required."))
            if (file.exists() && !file.delete()) error("Unable to delete note audio.")
            call.resolve()
        } catch (error: Throwable) {
            call.reject(error.message ?: "Unable to delete recording.", "AUDIO_DELETE_FAILED", error.asException())
        }
    }

    private fun managedFile(path: String, directory: String): File {
        val root = File(context.filesDir, directory).canonicalFile
        val file = File(path).canonicalFile
        check(file.parentFile == root) { "Audio path is outside app-private storage." }
        return file
    }

    private fun managedAudioFile(path: String): File {
        val file = File(path).canonicalFile
        val allowed = listOf("recordings", "note-audio")
            .map { File(context.filesDir, it).canonicalFile }
        check(allowed.any { file.parentFile == it }) { "Audio path is outside app-private storage." }
        return file
    }

    private fun statusObject() = JSObject().apply {
        put("recording", recording.get())
        put("startedAt", if (startedAt == 0L) null else startedAt)
        put("path", output?.absolutePath)
        put("error", failure)
        put("sampleRate", SAMPLE_RATE)
    }

    override fun handleOnDestroy() {
        recording.set(false)
        runCatching { recorder?.stop() }
        runCatching { worker?.join(2_000) }
        recorder?.release()
        output?.delete()
        recorder = null
        worker = null
        output = null
        context.stopService(Intent(context, AudioRecordingService::class.java))
        super.handleOnDestroy()
    }

    private fun pruneTemporaryRecordings() {
        val cutoff = System.currentTimeMillis() - TEMP_RETENTION_MS
        File(context.filesDir, "recordings").listFiles()?.forEach { file ->
            if (file.isFile && file.name.endsWith(".wav") && file.lastModified() < cutoff) {
                file.delete()
            }
        }
    }

    private fun recoverRetainedAudio() {
        val directory = File(context.filesDir, "note-audio")
        directory.listFiles()?.forEach { file ->
            when {
                file.name.matches(Regex("""\.note-(\d+)\.bak""")) -> {
                    val noteId = Regex("""\.note-(\d+)\.bak""").matchEntire(file.name)
                        ?.groupValues?.get(1)
                        ?: return@forEach
                    val destination = File(directory, "note-$noteId.wav")
                    if (destination.exists()) file.delete() else file.renameTo(destination)
                }
                file.name.endsWith(".part") -> file.delete()
            }
        }
    }

    companion object {
        const val SAMPLE_RATE = 16_000
        private const val CHANNEL = AudioFormat.CHANNEL_IN_MONO
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
        private const val MAX_RECORDING_BYTES = SAMPLE_RATE * 2L * 30L * 60L
        private const val TEMP_RETENTION_MS = 24L * 60L * 60L * 1000L
    }
}

private fun Throwable.asException(): Exception = this as? Exception ?: Exception(this)
