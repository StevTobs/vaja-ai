import re
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class Segment(BaseModel):
    id: int = Field(ge=0)
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(ge=0, allow_inf_nan=False)
    text: str = Field(max_length=50000)
    speaker: str | None = Field(default=None, pattern=r"^S\d{1,2}$")

    @model_validator(mode="after")
    def valid_interval(self):
        if self.end < self.start:
            raise ValueError("end must be >= start")
        return self


class EditTranscript(BaseModel):
    revision: int = Field(ge=0)
    segments: list[Segment] = Field(max_length=50000)
    reset: bool = False
    # Display names per speaker label, e.g. {"S1": "เจ้าหน้าที่"}; None keeps the current names.
    speaker_names: dict[str, str] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def valid_names(self):
        for key, name in (self.speaker_names or {}).items():
            if not re.fullmatch(r"S\d{1,2}", key) or not 0 < len(name.strip()) <= 50:
                raise ValueError("invalid speaker name")
        return self


InputKind = Literal["audio", "microphone", "video"]


class StartAnalysis(BaseModel):
    provider: Literal["ollama", "claude_cli", "claude_api"]


class ApplyAnalysis(BaseModel):
    revision: int = Field(ge=0)


class UpdateSettings(BaseModel):
    values: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=100)
    reset: list[str] = Field(default_factory=list, max_length=100)


class DownloadModel(BaseModel):
    name: str = Field(min_length=1, max_length=300)
