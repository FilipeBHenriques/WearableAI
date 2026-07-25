#include <jni.h>
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <limits>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

#ifdef WEARABLEAI_HAS_WHISPER
#include "whisper.h"
#endif
#ifdef WEARABLEAI_HAS_LLAMA
#include "llama.h"
#endif

namespace {
std::mutex inference_mutex;

#ifdef WEARABLEAI_HAS_WHISPER
whisper_context *cached_whisper = nullptr;
std::string cached_whisper_path;

void reset_whisper() {
    if (cached_whisper) whisper_free(cached_whisper);
    cached_whisper = nullptr;
    cached_whisper_path.clear();
}

whisper_context *load_whisper(const std::string &path) {
    if (path.empty()) throw std::runtime_error("Whisper model path is empty.");
    if (cached_whisper && cached_whisper_path == path) return cached_whisper;
    reset_whisper();
    cached_whisper = whisper_init_from_file_with_params(path.c_str(), whisper_context_default_params());
    if (!cached_whisper) throw std::runtime_error("Whisper model could not be loaded.");
    cached_whisper_path = path;
    return cached_whisper;
}
#endif

#ifdef WEARABLEAI_HAS_LLAMA
std::once_flag llama_backend_once;
bool llama_backend_initialized = false;
llama_model *cached_llama_model = nullptr;
llama_context *cached_llama_context = nullptr;
std::string cached_llama_path;

void ensure_llama_backend() {
    std::call_once(llama_backend_once, [] {
        llama_backend_init();
        llama_backend_initialized = true;
    });
}

void reset_llama() {
    if (cached_llama_context) llama_free(cached_llama_context);
    if (cached_llama_model) llama_model_free(cached_llama_model);
    cached_llama_context = nullptr;
    cached_llama_model = nullptr;
    cached_llama_path.clear();
}

llama_context *load_llama(const std::string &path) {
    if (path.empty()) throw std::runtime_error("Llama model path is empty.");
    if (cached_llama_context && cached_llama_model && cached_llama_path == path) {
        return cached_llama_context;
    }
    reset_llama();
    ensure_llama_backend();
    cached_llama_model = llama_model_load_from_file(path.c_str(), llama_model_default_params());
    if (!cached_llama_model) throw std::runtime_error("Llama model could not be loaded.");
    llama_context_params params = llama_context_default_params();
    params.n_ctx = 4096;
    params.n_batch = 512;
    params.n_seq_max = 1;
    cached_llama_context = llama_init_from_model(cached_llama_model, params);
    if (!cached_llama_context) {
        reset_llama();
        throw std::runtime_error("Llama context initialization failed.");
    }
    cached_llama_path = path;
    return cached_llama_context;
}

std::string format_llama_prompt(const std::string &content) {
    const char *chat_template = llama_model_chat_template(cached_llama_model, nullptr);
    if (!chat_template) throw std::runtime_error("Llama model has no supported chat template.");
    const llama_chat_message message{"user", content.c_str()};
    const int32_t required = llama_chat_apply_template(
        chat_template, &message, 1, true, nullptr, 0);
    if (required <= 0) throw std::runtime_error("Llama chat template could not be applied.");
    std::vector<char> formatted(static_cast<size_t>(required) + 1u);
    const int32_t written = llama_chat_apply_template(
        chat_template,
        &message,
        1,
        true,
        formatted.data(),
        static_cast<int32_t>(formatted.size()));
    if (written < 0 || written > required) {
        throw std::runtime_error("Llama chat prompt formatting failed.");
    }
    return std::string(formatted.data(), static_cast<size_t>(written));
}
#endif

std::string from_jstring(JNIEnv *env, jstring value) {
    if (!value) return {};
    jclass string_class = env->FindClass("java/lang/String");
    jmethodID get_bytes = env->GetMethodID(
        string_class, "getBytes", "(Ljava/lang/String;)[B");
    jstring charset = env->NewStringUTF("UTF-8");
    auto bytes = static_cast<jbyteArray>(env->CallObjectMethod(value, get_bytes, charset));
    env->DeleteLocalRef(charset);
    env->DeleteLocalRef(string_class);
    if (!bytes || env->ExceptionCheck()) return {};
    const jsize length = env->GetArrayLength(bytes);
    std::string result(static_cast<size_t>(length), '\0');
    if (length > 0) {
        env->GetByteArrayRegion(bytes, 0, length, reinterpret_cast<jbyte *>(result.data()));
    }
    env->DeleteLocalRef(bytes);
    return result;
}

jstring fail(JNIEnv *env, const std::string &message);

jstring to_jstring(JNIEnv *env, const std::string &value) {
    if (value.size() > static_cast<size_t>(std::numeric_limits<jsize>::max())) {
        return fail(env, "Native text result is too large.");
    }
    jbyteArray bytes = env->NewByteArray(static_cast<jsize>(value.size()));
    if (!bytes) return nullptr;
    if (!value.empty()) {
        env->SetByteArrayRegion(
            bytes,
            0,
            static_cast<jsize>(value.size()),
            reinterpret_cast<const jbyte *>(value.data()));
    }
    jclass string_class = env->FindClass("java/lang/String");
    jmethodID constructor = env->GetMethodID(
        string_class, "<init>", "([BLjava/lang/String;)V");
    jstring charset = env->NewStringUTF("UTF-8");
    auto result = static_cast<jstring>(
        env->NewObject(string_class, constructor, bytes, charset));
    env->DeleteLocalRef(charset);
    env->DeleteLocalRef(string_class);
    env->DeleteLocalRef(bytes);
    return result;
}

jstring fail(JNIEnv *env, const std::string &message) {
    jclass type = env->FindClass("java/lang/IllegalStateException");
    env->ThrowNew(type, message.c_str());
    return nullptr;
}

uint32_t u32(const uint8_t *p) {
    return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}

uint16_t u16(const uint8_t *p) {
    return uint16_t(p[0]) | (uint16_t(p[1]) << 8);
}

std::vector<float> read_wav_pcm16_mono(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("WAV input cannot be opened.");
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)), {});
    if (bytes.size() < 44 || std::string(reinterpret_cast<char *>(bytes.data()), 4) != "RIFF" ||
        std::string(reinterpret_cast<char *>(bytes.data() + 8), 4) != "WAVE") {
        throw std::runtime_error("Input is not a valid WAV file.");
    }
    uint16_t format = 0, channels = 0, bits = 0;
    uint32_t sample_rate = 0;
    const uint8_t *pcm = nullptr;
    size_t pcm_size = 0;
    for (size_t offset = 12; offset + 8 <= bytes.size();) {
        const std::string id(reinterpret_cast<char *>(bytes.data() + offset), 4);
        const uint32_t size = u32(bytes.data() + offset + 4);
        const size_t data = offset + 8;
        if (data + size > bytes.size()) throw std::runtime_error("WAV chunk is truncated.");
        if (id == "fmt " && size >= 16) {
            format = u16(bytes.data() + data);
            channels = u16(bytes.data() + data + 2);
            sample_rate = u32(bytes.data() + data + 4);
            bits = u16(bytes.data() + data + 14);
        } else if (id == "data") {
            pcm = bytes.data() + data;
            pcm_size = size;
        }
        offset = data + size + (size & 1u);
    }
    if (format != 1 || channels != 1 || bits != 16 || sample_rate != 16000 || !pcm) {
        throw std::runtime_error("Whisper requires 16 kHz mono 16-bit PCM WAV input.");
    }
    constexpr size_t max_pcm_bytes = 16000u * 2u * 30u * 60u;
    if (pcm_size == 0 || (pcm_size & 1u) != 0 || pcm_size > max_pcm_bytes) {
        throw std::runtime_error("WAV audio length is invalid or exceeds 30 minutes.");
    }
    std::vector<float> samples(pcm_size / 2);
    for (size_t i = 0; i < samples.size(); ++i) {
        samples[i] = static_cast<int16_t>(u16(pcm + i * 2)) / 32768.0f;
    }
    return samples;
}
} // namespace

extern "C" JNIEXPORT jstring JNICALL
Java_com_wearableai_local_ai_NativeInference_nativeStatus(JNIEnv *env, jobject) {
    std::string status = "{\"whisper\":";
#ifdef WEARABLEAI_HAS_WHISPER
    status += "true";
#else
    status += "false";
#endif
    status += ",\"llama\":";
#ifdef WEARABLEAI_HAS_LLAMA
    status += "true";
#else
    status += "false";
#endif
    status += "}";
    return to_jstring(env, status);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_wearableai_local_ai_NativeInference_nativeWarmup(
    JNIEnv *env, jobject, jstring whisper_path, jstring llama_path) {
    std::lock_guard<std::mutex> lock(inference_mutex);
    try {
        bool whisper_ready = false;
        bool llama_ready = false;
#ifdef WEARABLEAI_HAS_WHISPER
        const std::string whisper_model = from_jstring(env, whisper_path);
        if (!whisper_model.empty()) {
            load_whisper(whisper_model);
            whisper_ready = true;
        }
#endif
#ifdef WEARABLEAI_HAS_LLAMA
        const std::string llama_model_path = from_jstring(env, llama_path);
        if (!llama_model_path.empty()) {
            load_llama(llama_model_path);
            llama_ready = true;
        }
#endif
        return to_jstring(env, std::string("{\"whisperReady\":") +
            (whisper_ready ? "true" : "false") + ",\"llamaReady\":" +
            (llama_ready ? "true" : "false") + "}");
    } catch (const std::exception &error) {
#ifdef WEARABLEAI_HAS_WHISPER
        reset_whisper();
#endif
#ifdef WEARABLEAI_HAS_LLAMA
        reset_llama();
#endif
        return fail(env, error.what());
    }
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_wearableai_local_ai_NativeInference_nativeTranscribe(
    JNIEnv *env, jobject, jstring wav_path, jstring model_path) {
#ifndef WEARABLEAI_HAS_WHISPER
    return fail(env, "Whisper support was not compiled; vendor whisper.cpp and rebuild.");
#else
    std::lock_guard<std::mutex> lock(inference_mutex);
    try {
        const auto samples = read_wav_pcm16_mono(from_jstring(env, wav_path));
        whisper_context *ctx = load_whisper(from_jstring(env, model_path));
        auto params = whisper_full_default_params(WHISPER_SAMPLING_BEAM_SEARCH);
        params.beam_search.beam_size = 5;
        params.language = "en";
        params.translate = false;
        params.no_context = true;
        params.print_progress = false;
        params.print_realtime = false;
        params.print_timestamps = false;
        if (whisper_full(ctx, params, samples.data(), static_cast<int>(samples.size())) != 0) {
            throw std::runtime_error("Whisper transcription failed.");
        }
        std::string text;
        const int segments = whisper_full_n_segments(ctx);
        for (int i = 0; i < segments; ++i) text += whisper_full_get_segment_text(ctx, i);
        return to_jstring(env, text);
    } catch (const std::exception &error) {
        reset_whisper();
        return fail(env, error.what());
    }
#endif
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_wearableai_local_ai_NativeInference_nativeGenerate(
    JNIEnv *env, jobject, jstring prompt_value, jstring model_path, jint max_tokens) {
#ifndef WEARABLEAI_HAS_LLAMA
    return fail(env, "Llama support was not compiled; vendor llama.cpp and rebuild.");
#else
    std::lock_guard<std::mutex> lock(inference_mutex);
    try {
        llama_context *ctx = load_llama(from_jstring(env, model_path));
        const llama_vocab *vocab = llama_model_get_vocab(cached_llama_model);
        const std::string prompt = format_llama_prompt(from_jstring(env, prompt_value));
        if (prompt.size() > static_cast<size_t>(std::numeric_limits<int32_t>::max())) {
            throw std::runtime_error("Prompt is too large.");
        }
        const int32_t tokenized = llama_tokenize(
            vocab, prompt.c_str(), static_cast<int32_t>(prompt.size()), nullptr, 0, true, true);
        if (tokenized >= 0 || tokenized == std::numeric_limits<int32_t>::min()) {
            throw std::runtime_error("Prompt tokenization failed.");
        }
        const int32_t count = -tokenized;
        std::vector<llama_token> tokens(count);
        if (llama_tokenize(
                vocab,
                prompt.c_str(),
                static_cast<int32_t>(prompt.size()),
                tokens.data(),
                static_cast<int32_t>(tokens.size()),
                true,
                true) != count) {
            throw std::runtime_error("Prompt tokenization failed.");
        }
        const uint32_t context_size = llama_n_ctx(ctx);
        if (tokens.size() >= context_size) throw std::runtime_error("Prompt exceeds the model context.");
        llama_memory_clear(llama_get_memory(ctx), true);
        const int32_t batch_size = static_cast<int32_t>(llama_n_batch(ctx));
        if (batch_size <= 0) throw std::runtime_error("Llama context has an invalid batch size.");
        for (int32_t offset = 0; offset < count; offset += batch_size) {
            const int32_t length = std::min(batch_size, count - offset);
            if (llama_decode(ctx, llama_batch_get_one(tokens.data() + offset, length)) != 0) {
                throw std::runtime_error("Prompt evaluation failed.");
            }
        }
        std::unique_ptr<llama_sampler, decltype(&llama_sampler_free)> sampler(
            llama_sampler_init_greedy(), llama_sampler_free);
        if (!sampler) throw std::runtime_error("Greedy sampler initialization failed.");
        std::string output;
        const int token_limit = std::min<int>(
            std::max<int>(0, max_tokens), static_cast<int>(context_size - tokens.size()));
        for (int generated = 0; generated < token_limit; ++generated) {
            llama_token token = llama_sampler_sample(sampler.get(), ctx, -1);
            if (llama_vocab_is_eog(vocab, token)) break;
            char piece[256];
            int length = llama_token_to_piece(vocab, token, piece, sizeof(piece), 0, true);
            if (length < 0) {
                std::vector<char> dynamic_piece(-length);
                length = llama_token_to_piece(
                    vocab,
                    token,
                    dynamic_piece.data(),
                    static_cast<int32_t>(dynamic_piece.size()),
                    0,
                    true);
                if (length < 0) throw std::runtime_error("Generated token could not be decoded.");
                if (length > 0) output.append(dynamic_piece.data(), length);
            } else if (length > 0) {
                output.append(piece, length);
            }
            llama_sampler_accept(sampler.get(), token);
            llama_token next[] = {token};
            if (llama_decode(ctx, llama_batch_get_one(next, 1)) != 0) {
                throw std::runtime_error("Generated token evaluation failed.");
            }
        }
        return to_jstring(env, output);
    } catch (const std::exception &error) {
        reset_llama();
        return fail(env, error.what());
    }
#endif
}

extern "C" JNIEXPORT void JNICALL JNI_OnUnload(JavaVM *, void *) {
    std::lock_guard<std::mutex> lock(inference_mutex);
#ifdef WEARABLEAI_HAS_WHISPER
    reset_whisper();
#endif
#ifdef WEARABLEAI_HAS_LLAMA
    reset_llama();
    if (llama_backend_initialized) llama_backend_free();
#endif
}
