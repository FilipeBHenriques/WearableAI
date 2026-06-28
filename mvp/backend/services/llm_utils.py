"""Shared helpers for parsing LLM output."""

import json


def extract_json_object(raw_text: str) -> dict:
    try:
        return json.loads(raw_text.strip())
    except json.JSONDecodeError:
        pass

    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", raw_text, 0)

    return json.loads(raw_text[start : end + 1])
