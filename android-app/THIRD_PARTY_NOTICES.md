# Third-party production artifacts

The artifacts below are downloaded only when `npm run prepare:production` is
run. Exact revisions, files, sizes, and checksums are recorded in
`packaging/model-lock.json` and the generated model manifest.

- **whisper.cpp v1.9.1** and the **ggml-base.en Q5_1** model, by Georgi
  Gerganov and contributors. Source and code license: MIT.
  <https://github.com/ggerganov/whisper.cpp>
- **llama.cpp b10067**, by Georgi Gerganov and contributors. Code license:
  MIT. <https://github.com/ggerganov/llama.cpp>
- **Qwen2.5-1.5B-Instruct Q4_K_M GGUF**, quantized and distributed by
  bartowski from the Qwen model. Model license: Apache License 2.0.
  <https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF>
- **Xenova/all-MiniLM-L6-v2** quantized ONNX model and vocabulary, derived
  from sentence-transformers/all-MiniLM-L6-v2. Model license: Apache License
  2.0. <https://huggingface.co/Xenova/all-MiniLM-L6-v2>

The downloaded native source trees retain their upstream license files. Model
users and distributors remain responsible for complying with all upstream
license terms and notices.
