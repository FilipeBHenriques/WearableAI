# WearableAI Android

This directory is a standalone Android port of the WearableAI MVP. The original
`mvp/` application is not used or modified at runtime.

## Stack

- React, TypeScript, Vite, and Capacitor for the interface and domain pipeline
- Android/Kotlin plugins for microphone, location, storage, and native bridges
- `whisper.cpp` with `ggml-base.en-q5_1` for offline speech recognition
- ONNX Runtime with `all-MiniLM-L6-v2` int8 for offline embeddings
- `llama.cpp` with Qwen2.5 1.5B Instruct Q4_K_M for offline text reasoning
- SQLite and app-private WAV storage

The production build uses exactly three model families: Whisper, MiniLM, and
Qwen. No network service, FastAPI process, Python runtime, or Ollama daemon is
required on the phone.

## Set up

Requirements:

- Node.js 22 or newer
- JDK 21
- Android SDK 36, NDK, and CMake 3.22.1
- An arm64 Android phone with at least 8 GB RAM and roughly 3 GB free storage

```bash
npm install
npm run prepare:production
npm test
npm run build
```

`prepare:production` downloads immutable, pinned model and native-source
artifacts, verifies their sizes and checksums, and generates the production
model manifest. Details and licenses are in `packaging/model-lock.json` and
`THIRD_PARTY_NOTICES.md`.

## Run and package

```bash
# One command: sync web UI, prepare models/sources, build sideload APK
npm run release

# Browser demo with in-memory storage and deterministic fallbacks
npm run dev

# Android debug build; models are intentionally omitted
npm run android:build

# Play AAB with an install-time model asset pack
npm run android:release:play
```

Release tasks fail if any model, checksum, generated manifest, or pinned native
source tree is missing. The Play build does not duplicate the model payload in
the base application.

## Privacy

Audio, notes, locations, embeddings, and model inference remain on the device.
The app requests microphone and location access only for recording and nearby
note suggestions. Android data backup is disabled.
