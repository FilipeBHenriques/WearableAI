# WearableAI Android

This is the native Capacitor 8 host for `com.wearableai.local`. It targets API 36,
requires API 24+, and packages only `arm64-v8a`.

## Reproducible production artifacts

From `android-app`, run:

```text
npm run prepare:production
```

The built-in Node ESM preparer downloads and verifies every locked model,
safely extracts pinned GitHub source tarballs, and atomically generates the
model manifest. It is idempotent. `npm run verify:production` performs the
same verification without downloading or changing artifacts. The immutable
inputs are in `packaging/model-lock.json`; downloaded artifacts remain
ignored by Git.

The MiniLM vocabulary is pinned by both Hugging Face commit and Git blob
identity. Its locked size is checked during download; its SHA-256 is computed
from the downloaded blob and written to the generated
`model-manifest.json`.

## Release distributions

- `npm run android:release:sideload` builds `sideloadRelease`. Models are
  included in the APK assets.
- `npm run android:release:play` builds `playRelease` as an AAB. Models are
  included only in the install-time `wearable_ai_models` asset pack.

Both variants read one canonical prepared directory containing exactly three
model weights (Whisper, MiniLM, and Qwen) plus MiniLM's vocabulary:
`models-pack/src/main/assets/models`. The Play Gradle invocation requires
`-PwithPlayAssetPack=true`; omitting it fails instead of silently producing an
AAB without models. Release pre-build validation streams SHA-256 checks for
all four files, checks exact sizes, and recomputes both native source-tree
checksums against their pinned receipts.

CMake detects prepared native trees and defines `WEARABLEAI_HAS_WHISPER` and
`WEARABLEAI_HAS_LLAMA`. Debug builds intentionally package no models and
report that production AI is unavailable.

## Build notes

The text wrapper launchers are included, but the binary
`gradle/wrapper/gradle-wrapper.jar` cannot be represented in this scaffold.
Generate it with Gradle 8.13 (`gradle wrapper`) or copy the matching wrapper
JAR before using `gradlew`. The launchers fall back to a system `gradle`
command when available.

Capacitor sync will replace the placeholder web assets with the Vite build.
