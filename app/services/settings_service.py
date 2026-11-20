"""Settings page: describe every setting, validate and save UI overrides, manage model downloads."""
import threading

from annotated_types import Ge, Le
from pydantic import ValidationError

from app.config import BOOTSTRAP_FIELDS, SECRET_FIELDS, LiveSettings, Settings
from app.services.diarization_service import DiarizationService
from app.services.media_service import AppError

SPEAKER_MODEL = "speaker-diarization"

# applies: now = immediately; next_job = worker reloads the model on the next job; restart = edit .env + restart
GROUPS = [
    ("asr", "การถอดเสียง (ASR)", "มีผลกับงานถัดไป worker โหลดโมเดลใหม่ให้อัตโนมัติ", "next_job", [
        ("asr_model", "โมเดลถอดเสียง", "ชื่อโมเดล faster-whisper หรือ Hugging Face repo ต้องดาวน์โหลดก่อนใช้"),
        ("asr_fallback_model", "โมเดลสำรอง", "ใช้ถอดใหม่เฉพาะช่วงที่พบข้อความหลอน ว่างไว้ = ตัดช่วงนั้นออก"),
        ("asr_device", "อุปกรณ์ประมวลผล", "cuda ต้องมี NVIDIA GPU และติดตั้ง runtime แล้ว"),
        ("asr_compute_type", "ชนิดการคำนวณ", "CPU ใช้ int8, GPU ใช้ float16"),
        ("asr_language", "ภาษา", "รหัสภาษา เช่น th"),
        ("asr_batch_size", "Batch size", "1 = ปกติ, 8 = เร็วขึ้นบน GPU แต่ใช้ VRAM มากขึ้น"),
        ("asr_beam_size", "Beam size", "5 = แม่นกว่า, 1 = เร็วกว่า"),
        ("asr_cpu_threads", "จำนวน CPU threads", ""),
        ("asr_vad", "ตัดช่วงเงียบ (VAD)", "ข้ามช่วงที่ไม่มีเสียงพูด"),
        ("asr_timestamps", "ใช้ timestamp tokens", "ปิดสำหรับโมเดล fine-tune ที่ไม่ได้ฝึก timestamp เช่น Thonburian"),
        ("asr_chunk_length", "ความยาวช่วงถอดรหัส (วินาที)", "0 = ค่าเริ่มต้นของโมเดล (30), Thonburian แนะนำ 10"),
        ("model_local_files_only", "ห้ามดาวน์โหลดโมเดลระหว่างถอดเสียง", "เปิดไว้เพื่อให้ worker ทำงาน offline"),
        ("asr_timeout_seconds", "เวลาถอดเสียงสูงสุด (วินาที)", "รวมเวลาโหลดโมเดล"),
    ]),
    ("quality", "คุณภาพภาษาไทย", "มีผลกับงานถัดไป", "next_job", [
        ("asr_initial_prompt", "คำศัพท์นำทาง (initial prompt)", "เช่น ค่าไฟ มิเตอร์ การไฟฟ้า บิล"),
        ("asr_hotwords", "Hotwords", "คำเฉพาะที่ต้องการให้สะกดถูก"),
        ("asr_repetition_penalty", "ลงโทษคำซ้ำ", "1.0 = ปิด, 1.1 แนะนำ"),
        ("asr_no_repeat_ngram_size", "ห้าม n-gram ซ้ำ", "0 = ปิด"),
        ("asr_collapse_repeats", "ยุบข้อความวนซ้ำเมื่อซ้ำเกิน (ครั้ง)", "0 = ปิด"),
        ("asr_audio_filter", "ตัวกรองเสียงก่อนส่งโมเดล", "FFmpeg filter เช่น highpass=f=100,dynaudnorm=f=150:g=15 ว่าง = ปิด"),
        ("asr_hallucination_markers", "ข้อความหลอนที่ต้องตรวจจับ", "คั่นด้วย | segment ที่มีคำเหล่านี้จะถูกถอดใหม่ด้วยโมเดลสำรอง"),
    ]),
    ("speakers", "แยกผู้พูด", "แยกจากเสียงในเครื่องนี้ (ไม่ส่งข้อมูลออก) มีผลกับงานถัดไป", "next_job", [
        ("diarization_enabled", "แยกผู้พูดอัตโนมัติหลังถอดเสียง", "ติดป้าย ผู้พูด 1, ผู้พูด 2 … ให้แต่ละช่วง แก้ชื่อได้ในหน้าตรวจทาน"),
        ("diarization_num_speakers", "จำนวนผู้พูด", "2 = สายสนทนาทั่วไป, 0 = ให้ระบบนับเอง"),
        ("diarization_threshold", "ความไวในการแยกเสียง", "ใช้เมื่อจำนวนผู้พูด = 0; ค่าน้อย = แยกเป็นหลายคนง่ายขึ้น"),
    ]),
    ("limits", "ไฟล์และพื้นที่จัดเก็บ", "มีผลทันที", "now", [
        ("max_upload_mb", "ขนาดไฟล์สูงสุด (MB)", ""),
        ("max_duration_seconds", "ความยาวสื่อสูงสุด (วินาที)", "7200 = 2 ชั่วโมง"),
        ("disk_quota_mb", "โควตาพื้นที่งานทั้งหมด (MB)", "ไม่รวม model cache"),
        ("min_free_disk_mb", "พื้นที่ว่างขั้นต่ำที่ต้องเหลือ (MB)", ""),
        ("ffmpeg_timeout_seconds", "เวลา FFmpeg สูงสุด (วินาที)", ""),
        ("job_poll_seconds", "รอบตรวจคิวของ worker (วินาที)", ""),
    ]),
    ("analysis", "AI วิเคราะห์ข้อความ", "มีผลทันที", "now", [
        ("analysis_providers", "ตัวเลือกที่เปิดใช้", "Claude Code และ Claude API ส่งข้อความ transcript ไปที่ Anthropic"),
        ("analysis_timeout_seconds", "เวลาวิเคราะห์สูงสุด (วินาที)", ""),
        ("ollama_url", "Ollama URL", ""),
        ("ollama_model", "โมเดล Ollama", "ต้อง ollama pull ก่อน เช่น qwen3:8b"),
        ("ollama_num_ctx", "Context ของ Ollama (tokens)", "บทสนทนายาวต้องใช้ค่ามาก"),
        ("claude_cli_model", "โมเดล Claude Code", "เช่น opus, sonnet หรือชื่อเต็ม"),
        ("claude_api_model", "โมเดล Claude API", "เช่น claude-opus-5-5"),
        ("claude_effort", "ระดับการคิดของ Claude API", "สูงขึ้น = ละเอียดขึ้นแต่ช้าและแพงขึ้น"),
        ("anthropic_api_key", "Anthropic API key", "ว่างไว้ = ใช้ ANTHROPIC_API_KEY หรือ ant auth login ของเครื่อง"),
    ]),
    ("system", "ระบบ (แก้ใน .env แล้วรีสตาร์ท)", "ค่าที่เกี่ยวกับการเริ่มโปรแกรม ความปลอดภัย และ path จึงแก้จากหน้าเว็บไม่ได้", "restart", [
        ("app_env", "โหมด", "local หรือ server"),
        ("host", "Host", ""), ("port", "Port", ""),
        ("data_dir", "โฟลเดอร์ข้อมูล", ""), ("model_cache_dir", "โฟลเดอร์โมเดล", ""),
        ("claude_cli_path", "คำสั่ง Claude Code", ""),
        ("api_token", "API token", "รหัสผ่าน HTTP Basic (username vaja)"),
        ("worker_concurrency", "จำนวน worker", "MVP รองรับ 1"),
    ]),
]
OPTIONS = {
    "asr_device": ["cpu", "cuda", "auto"],
    "asr_compute_type": ["int8", "int8_float16", "float16", "float32", "auto"],
    "claude_effort": ["low", "medium", "high", "xhigh", "max"],
}
MULTI = {"analysis_providers": [("ollama", "Local LLM (Ollama) · ในเครื่อง"),
                                ("claude_cli", "Claude Code · ส่งข้อความไป Anthropic"),
                                ("claude_api", "Claude API · ส่งข้อความไป Anthropic")]}
SUGGESTIONS = {
    "asr_model": ["small", "medium", "large-v3", "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                  "Vinxscribe/biodatlab-whisper-th-large-v3-faster"],
    "asr_fallback_model": ["mobiuslabsgmbh/faster-whisper-large-v3-turbo", "large-v3"],
    "claude_cli_model": ["opus", "sonnet", "haiku"],
    "claude_api_model": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"],
}
EDITABLE = {key for _, _, _, applies, fields in GROUPS if applies != "restart" for key, _, _ in fields}
assert EDITABLE.isdisjoint(BOOTSTRAP_FIELDS)
assert {key for *_, fields in GROUPS for key, _, _ in fields} == set(Settings.model_fields)


def _kind(field):
    return {bool: "bool", int: "int", float: "float"}.get(field.annotation, "text")


def _bounds(field):
    lo = next((m.ge for m in field.metadata if isinstance(m, Ge)), None)
    hi = next((m.le for m in field.metadata if isinstance(m, Le)), None)
    return lo, hi


class SettingsService:
    def __init__(self, settings: LiveSettings):
        self.settings = settings
        self.downloads, self._dl_lock = {}, threading.Lock()

    def describe(self):
        current, overrides = self.settings.current(), self.settings.overrides()
        base_set = self.settings.base.model_fields_set
        groups = []
        for gid, title, note, applies, fields in GROUPS:
            items = []
            for key, label, help_text in fields:
                field = Settings.model_fields[key]
                value = getattr(current, key)
                secret = key in SECRET_FIELDS
                lo, hi = _bounds(field)
                items.append({
                    "key": key, "label": label, "help": help_text, "type": "multi" if key in MULTI else _kind(field),
                    "value": None if secret else value, "is_set": bool(value) if secret else None,
                    "default": None if secret else field.default,
                    "source": "ui" if key in overrides else "env" if key in base_set else "default",
                    "editable": key in EDITABLE, "secret": secret, "min": lo, "max": hi,
                    "options": OPTIONS.get(key), "choices": MULTI.get(key), "suggestions": SUGGESTIONS.get(key),
                })
            groups.append({"id": gid, "title": title, "note": note, "applies": applies, "fields": items})
        return {"groups": groups, "error": self.settings.error, "models": self.models()}

    def update(self, values: dict, reset: list[str]):
        unknown = [k for k in [*values, *reset] if k not in EDITABLE]
        if unknown:
            raise AppError("SETTING_READ_ONLY", f"แก้จากหน้าเว็บไม่ได้: {', '.join(unknown)}", 400)
        overrides = self.settings.overrides()
        for key in reset:
            overrides.pop(key, None)
        for key, value in values.items():
            if key in SECRET_FIELDS and value is None:
                continue  # unchanged secret
            overrides[key] = value
        try:
            self.settings.save(overrides)
        except ValidationError as exc:
            messages = []
            for err in exc.errors():
                where = ".".join(str(p) for p in err["loc"]) or "settings"
                messages.append(f"{where}: {err['msg'].removeprefix('Value error, ')}")
            raise AppError("INVALID_SETTINGS", "ค่าไม่ถูกต้อง · " + " · ".join(messages), 422)
        return self.describe()

    # ---- ASR model cache -------------------------------------------------------
    def models(self):
        cfg = self.settings.current()
        names = list(dict.fromkeys(filter(None, (cfg.asr_model, cfg.asr_fallback_model))))
        with self._dl_lock:
            jobs = dict(self.downloads)
        models = {name: {"cached": self._cached(name, cfg.model_cache_dir), **jobs.get(name, {})} for name in names}
        models[SPEAKER_MODEL] = {"cached": DiarizationService(cfg).ready(), **jobs.get(SPEAKER_MODEL, {})}
        return models

    @staticmethod
    def _cached(name, cache_dir):
        try:
            from faster_whisper.utils import download_model
            download_model(name, local_files_only=True, cache_dir=cache_dir)
            return True
        except Exception:
            return False

    def download(self, name):
        cfg = self.settings.current()
        if name not in (cfg.asr_model, cfg.asr_fallback_model, SPEAKER_MODEL):
            raise AppError("MODEL_NOT_CONFIGURED", "ดาวน์โหลดได้เฉพาะโมเดลที่ตั้งค่าไว้", 400)
        with self._dl_lock:
            if self.downloads.get(name, {}).get("download") == "running":
                raise AppError("DOWNLOAD_RUNNING", "กำลังดาวน์โหลดโมเดลนี้อยู่", 409)
            self.downloads[name] = {"download": "running", "error": None}

        def run():
            try:
                if name == SPEAKER_MODEL:
                    DiarizationService(cfg).download()
                else:
                    from faster_whisper.utils import download_model
                    download_model(name, cache_dir=cfg.model_cache_dir)
                state = {"download": "done", "error": None}
            except Exception as exc:
                state = {"download": "failed", "error": type(exc).__name__}
            with self._dl_lock:
                self.downloads[name] = state
        threading.Thread(target=run, daemon=True, name=f"download-{name}").start()
        return {"download": "running"}
