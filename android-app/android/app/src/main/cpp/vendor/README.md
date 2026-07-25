# Prepared native sources

This directory is populated by `npm run prepare:production:sources`.

The preparation script downloads immutable `whisper.cpp` and `llama.cpp`
GitHub source archives at the revisions in `packaging/model-lock.json`, safely
extracts each archive, and writes a `.wearableai-source.json` receipt into each
tree. Downloaded trees and receipts are intentionally ignored by Git. Release
validation requires both trees, matching pinned commits, and matching
source-tree checksums from those receipts.
