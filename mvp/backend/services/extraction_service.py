"""Future home for structured note extraction.

Extraction is not persisted yet. When enabled, this service should derive:
summary, who, what, when, where, and actions from note text.
"""

from dataclasses import dataclass, field


@dataclass
class ExtractionResult:
    summary: str | None = None
    who: list[str] = field(default_factory=list)
    what: str | None = None
    when: str | None = None
    where: str | None = None
    actions: list[str] = field(default_factory=list)
