"""Owns shared local model instances and startup warmup."""

import os
import json
import logging
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from services.service_logger import log_service_call, log_service_step

os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

SENTENCE_MODEL_NAME = os.getenv("SENTENCE_MODEL_NAME", "all-MiniLM-L6-v2")
WHISPER_MODEL_NAME = os.getenv("WHISPER_MODEL_NAME", "base")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
REQUESTED_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL")
OLLAMA_HEALTH_TIMEOUT = int(os.getenv("OLLAMA_HEALTH_TIMEOUT", "10"))
OLLAMA_GENERATE_TIMEOUT = int(os.getenv("OLLAMA_GENERATE_TIMEOUT", "120"))
OLLAMA_MODEL_PREFERENCES = [
    "llama3:latest",
    "mistral:latest",
    "gemma:latest",
    "qwen2.5vl:3b",
    "gemma4:latest",
    "gpt-oss:20b",
]

for logger_name in (
    "sentence_transformers",
    "transformers",
    "huggingface_hub",
    "httpx",
    "urllib3",
    "torch",
):
    logging.getLogger(logger_name).setLevel(logging.WARNING)

_sentence_model = None
_sentence_model_lock = threading.Lock()

_whisper_model = None
_whisper_model_lock = threading.Lock()

ModelLoader = tuple[str, Callable[[], None]]


@log_service_call
def get_sentence_model():
    global _sentence_model
    with _sentence_model_lock:
        if _sentence_model is None:
            log_service_step("loading sentence model", model=SENTENCE_MODEL_NAME)
            from sentence_transformers import SentenceTransformer

            _sentence_model = SentenceTransformer(SENTENCE_MODEL_NAME)
    return _sentence_model


@log_service_call
def get_whisper_model():
    global _whisper_model
    with _whisper_model_lock:
        if _whisper_model is None:
            log_service_step(
                "loading whisper model",
                model=WHISPER_MODEL_NAME,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
            )
            from faster_whisper import WhisperModel

            _whisper_model = WhisperModel(
                WHISPER_MODEL_NAME,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
            )
    return _whisper_model


def _ollama_json(path: str, payload: dict[str, Any] | None = None, timeout: int = OLLAMA_HEALTH_TIMEOUT) -> dict[str, Any]:
    url = f"{OLLAMA_BASE_URL}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _ollama_tags() -> dict[str, Any]:
    try:
        return _ollama_json("/api/tags")
    except (OSError, URLError) as exc:
        if not shutil.which("ollama"):
            raise exc

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )

    last_error = None
    for _ in range(20):
        time.sleep(0.5)
        try:
            return _ollama_json("/api/tags")
        except (OSError, URLError) as exc:
            last_error = exc

    raise last_error or RuntimeError("Ollama did not start.")


def _select_ollama_model(available_models: list[str]) -> str | None:
    if REQUESTED_OLLAMA_MODEL:
        return REQUESTED_OLLAMA_MODEL

    for model_name in OLLAMA_MODEL_PREFERENCES:
        if model_name in available_models:
            return model_name

    return available_models[0] if available_models else None


@log_service_call
def get_llm_config_status() -> dict[str, Any]:
    try:
        tags = _ollama_tags()
    except (OSError, URLError) as exc:
        return {
            "configured": False,
            "ready": False,
            "base_url": OLLAMA_BASE_URL,
            "model": REQUESTED_OLLAMA_MODEL,
            "available_models": [],
            "error": f"Ollama is not reachable: {exc}",
        }

    available_models = sorted(
        {
            model_name
            for model in tags.get("models", [])
            for model_name in (model.get("name"), model.get("model"))
            if model_name
        }
    )
    selected_model = _select_ollama_model(available_models)
    if selected_model is None:
        return {
            "configured": False,
            "ready": False,
            "base_url": OLLAMA_BASE_URL,
            "model": None,
            "available_models": available_models,
            "error": "No Ollama models are installed.",
        }

    if selected_model not in available_models:
        return {
            "configured": False,
            "ready": False,
            "base_url": OLLAMA_BASE_URL,
            "model": selected_model,
            "available_models": available_models,
            "error": f"Ollama model '{selected_model}' is not installed.",
        }

    return {
        "configured": True,
        "ready": True,
        "base_url": OLLAMA_BASE_URL,
        "model": selected_model,
        "available_models": available_models,
        "error": None,
    }


@log_service_call
def generate_llm(prompt: str, max_tokens: int = 8, json_mode: bool = False) -> str:
    llm_status = get_llm_config_status()
    if not llm_status["configured"]:
        raise RuntimeError(str(llm_status["error"]))

    payload = {
        "model": llm_status["model"],
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0,
        },
    }
    if json_mode:
        payload["format"] = "json"

    response = _ollama_json(
        "/api/generate",
        payload,
        timeout=OLLAMA_GENERATE_TIMEOUT,
    )
    return str(response.get("response", "")).strip()


@log_service_call
def warm_classification_model() -> None:
    get_sentence_model()


@log_service_call
def warm_recording_model() -> None:
    get_whisper_model()


@log_service_call
def warm_relationship_model() -> None:
    status = get_llm_config_status()
    if status["configured"]:
        log_service_step("checking relationship llm", model=status["model"])
        generate_llm("Return exactly: OK", max_tokens=2)
    else:
        log_service_step("relationship llm disabled", error=status["error"])


@log_service_call
def warm_location_model() -> None:
    from services import location_service

    location_service.warm_up()


_model_loaders: list[ModelLoader] = [
    ("classification", warm_classification_model),
    ("location", warm_location_model),
    ("recording", warm_recording_model),
    ("relationship", warm_relationship_model),
]

_state: dict[str, Any] = {
    "ready": False,
    "started_at": None,
    "completed_at": None,
    "models": {
        name: {
            "status": "pending",
            "error": None,
            "started_at": None,
            "completed_at": None,
        }
        for name, _ in _model_loaders
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@log_service_call
def warm_up_all() -> None:
    """Warm shared models in a known-safe order before serving requests."""
    _state["ready"] = False
    _state["started_at"] = _now()
    _state["completed_at"] = None

    for name, load_model in _model_loaders:
        model_state = _state["models"][name]
        model_state["status"] = "warming"
        model_state["error"] = None
        model_state["started_at"] = _now()
        model_state["completed_at"] = None

        log_service_step("warming model", name=name)
        try:
            load_model()
        except Exception as exc:
            model_state["status"] = "failed"
            model_state["error"] = repr(exc)
            model_state["completed_at"] = _now()
            log_service_step("model failed", name=name, error=repr(exc))
            raise

        model_state["status"] = "ready"
        model_state["completed_at"] = _now()
        log_service_step("model ready", name=name)

    _state["ready"] = True
    _state["completed_at"] = _now()
    log_service_step("all models ready")


@log_service_call
def get_status() -> dict[str, Any]:
    return {
        "ready": _state["ready"],
        "started_at": _state["started_at"],
        "completed_at": _state["completed_at"],
        "llm": get_llm_config_status(),
        "models": {
            name: model_state.copy()
            for name, model_state in _state["models"].items()
        },
    }
