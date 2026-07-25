# Prepared production models

Run `npm run prepare:production:models` from `android-app`.

The three generated model weights, MiniLM vocabulary, and
`model-manifest.json` are ignored by Git. This single directory is the
canonical payload for both production distributions:

- `sideloadRelease` packages it in the APK base assets.
- `playRelease` packages it only in the install-time `wearable_ai_models`
  Play Asset Delivery pack.

Debug variants have no model asset source. Do not manually copy this directory
into `app/src/main/assets`.
