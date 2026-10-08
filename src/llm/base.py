"""What the rest of the app knows about an LLM: one method, no provider details."""
from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """The LLM call failed (timeout, HTTP error, rate limit, unusable response envelope)."""


@dataclass(frozen=True)
class ImagePart:
    mime: str
    data: bytes


class JSONVisionClient(Protocol):
    def complete_json(self, *, system: str, user_text: str, images: list[ImagePart],
                      schema_name: str, schema: dict) -> str:
        """Return the model's raw text answer (expected to be JSON matching `schema`).

        Raises LLMError for transport / HTTP failures. Does NOT validate the JSON.
        """
        ...
