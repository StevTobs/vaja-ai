from typing import Callable, Protocol


class ASREngine(Protocol):
    def transcribe(self, path: str, language: str, on_progress: Callable[[dict], None] | None = None) -> dict: ...
