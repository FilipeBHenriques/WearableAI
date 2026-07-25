"""Duration clamping primitive.

LLM-based duration estimation lives in memory_extraction_service now, which reuses
clamp_minutes here.
"""


def clamp_minutes(value: int) -> int:
    return max(0, min(value, 60 * 24 * 14))
