import json
import os
import re
import threading
import time
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator

# FFmpeg installed by the one-click installer lives next to the app (tools/ffmpeg/bin), not in the
# machine's PATH; expose it to this process and every child (API, worker, inference).
APP_ROOT = Path(__file__).resolve().parent.parent
_bundled_ffmpeg = APP_ROOT / "tools" / "ffmpeg" / "bin"
if _bundled_ffmpeg.is_dir() and str(_bundled_ffmpeg) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(_bundled_ffmpeg) + os.pathsep + os.environ.get("PATH", "")
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: str = "./data"
    max_upload_mb: int = Field(default=100, ge=1)
    max_duration_seconds: int = Field(default=7200, ge=1)
    asr_model: str = "small"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    asr_language: str = "th"
    worker_concurrency: int = 1
    ffmpeg_timeout_seconds: int = 600
    job_poll_seconds: int = 3
    model_cache_dir: str = "./data/models"
    model_local_files_only: bool = True
    asr_timeout_seconds: int = Field(default=3600, ge=1)
    disk_quota_mb: int = Field(default=10240, ge=1)
    min_free_disk_mb: int = Field(default=256, ge=0)
    api_token: str = ""
    asr_vad: bool = True
    asr_cpu_threads: int = Field(default=4, ge=1)
    asr_beam_size: int = Field(default=5, ge=1, le=10)
    asr_batch_size: int = Field(default=1, ge=1, le=32)
    # Domain vocabulary hint (e.g. "ค่าไฟ มิเตอร์ การไฟฟ้า"); biases spelling, not content.
    asr_initial_prompt: str = Field(default="", max_length=500)
    asr_hotwords: str = Field(default="", max_length=500)
    asr_repetition_penalty: float = Field(default=1.1, ge=1.0, le=2.0)
    asr_no_repeat_ngram_size: int = Field(default=0, ge=0, le=20)
    # Collapse runs of the same phrase repeated this many times (Whisper loop hallucination); 0 disables.
    asr_collapse_repeats: int = Field(default=4, ge=0, le=50)
    # FFmpeg filter for the model's copy only; normalizes quiet/uneven phone audio. Empty disables.
    asr_audio_filter: str = Field(default="highpass=f=100,dynaudnorm=f=150:g=15", max_length=500)
    # Seconds per decode window; 0 keeps the model default (30). Thai fine-tunes hallucinate less at 10.
    asr_chunk_length: int = Field(default=0, ge=0, le=30)
    # Fine-tunes trained without timestamp tokens (e.g. Thonburian) need false.
    asr_timestamps: bool = True
    # Substrings a fine-tune emits from training-data memory, not from the audio; "|" separated.
    asr_hallucination_markers: str = Field(default="", max_length=2000)
    # Model that re-transcribes only segments with a marker; empty leaves those segments out.
    asr_fallback_model: str = ""

    # Speaker separation from the voice (local, CPU). 0 speakers = detect automatically by threshold.
    diarization_enabled: bool = True
    diarization_num_speakers: int = Field(default=2, ge=0, le=10)
    diarization_threshold: float = Field(default=0.5, ge=0.1, le=1.5)

    # Transcript analysis (correction / summary / sentiment / topics) after ASR. Off unless listed.
    # Comma-separated: ollama (local, offline), claude_cli (Claude Code login), claude_api (API key).
    analysis_providers: str = ""
    analysis_timeout_seconds: int = Field(default=900, ge=30, le=7200)
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    ollama_num_ctx: int = Field(default=32768, ge=2048, le=262144)
    claude_cli_path: str = "claude"
    claude_cli_model: str = "opus"
    claude_api_model: str = "claude-opus-5-5"
    claude_effort: str = Field(default="medium", pattern="^(low|medium|high|xhigh|max)$")
    anthropic_api_key: str = ""

    @property
    def enabled_analysis_providers(self) -> list[str]:
        known = ("ollama", "claude_cli", "claude_api")
        return [p for p in (x.strip() for x in self.analysis_providers.split(",")) if p in known]

    @model_validator(mode="after")
    def validate_mode(self):
        if self.worker_concurrency != 1:
            raise ValueError("MVP requires WORKER_CONCURRENCY=1")
        if self.app_env != "local" and len(self.api_token) < 32:
            raise ValueError("Server mode requires API_TOKEN of at least 32 characters")
        if not self.ollama_url.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_URL must start with http:// or https://")
        validate_audio_filter(self.asr_audio_filter)
        return self

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# Audio filters are editable from the UI, so only plain signal-processing filters are allowed:
# FFmpeg filters such as movie/amovie/ametadata can read or write arbitrary files.
AUDIO_FILTERS = {"highpass", "lowpass", "bandpass", "bandreject", "dynaudnorm", "loudnorm", "speechnorm",
                 "afftdn", "anlmdn", "volume", "acompressor", "agate", "equalizer", "aresample", "silenceremove"}


def validate_audio_filter(chain: str):
    for part in filter(None, (p.strip() for p in chain.split(","))):
        name, _, args = part.partition("=")
        if name not in AUDIO_FILTERS or not re.fullmatch(r"[A-Za-z0-9_.:=\-]*", args):
            raise ValueError(f"ASR_AUDIO_FILTER allows only: {', '.join(sorted(AUDIO_FILTERS))}")


# Fixed at process start or security-sensitive (paths, executables, auth): edited in .env only.
BOOTSTRAP_FIELDS = ("app_env", "host", "port", "data_dir", "worker_concurrency", "api_token",
                    "model_cache_dir", "claude_cli_path")
SECRET_FIELDS = ("api_token", "anthropic_api_key")


class LiveSettings:
    """Settings that follow UI edits without a restart.

    Precedence: data/settings.json (saved from the UI) > environment / .env > defaults.
    The overrides file lives in the shared data volume so the API and worker (and Docker
    containers) see the same values; every attribute read returns the latest values.
    """

    def __init__(self, base: Settings | None = None):
        self.base = base or Settings()
        self.path = Path(self.base.data_dir).resolve() / "settings.json"
        self._lock = threading.Lock()
        self._stamp, self._checked, self._current, self.error = None, 0.0, self.base, None

    def overrides(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        return {k: v for k, v in data.items() if k in Settings.model_fields and k not in BOOTSTRAP_FIELDS}

    def build(self, overrides: dict) -> Settings:
        # Explicit init values outrank environment variables and .env in pydantic-settings.
        return Settings(_env_file=None, **{**self.base.model_dump(), **overrides})

    def current(self) -> Settings:
        now = time.monotonic()
        with self._lock:
            if now - self._checked < 1:
                return self._current
            self._checked = now
            try:
                stat = self.path.stat()
                stamp = (stat.st_mtime_ns, stat.st_size)
            except FileNotFoundError:
                stamp = None
            if stamp != self._stamp:
                self._stamp = stamp
                try:
                    self._current, self.error = self.build(self.overrides()), None
                except (ValueError, OSError) as exc:  # corrupt file: keep running on .env values
                    self._current, self.error = self.base, str(exc)
            return self._current

    def save(self, overrides: dict):
        self.build(overrides)  # raises ValidationError before anything is written
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
        with self._lock:
            self._checked = 0.0

    def __getattr__(self, name):
        return getattr(self.current(), name)


def snapshot(settings) -> Settings:
    """Plain, picklable Settings for child processes."""
    return settings.current() if isinstance(settings, LiveSettings) else settings


@lru_cache
def get_settings() -> LiveSettings:
    return LiveSettings()
