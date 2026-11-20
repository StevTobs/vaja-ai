import json
import math
import subprocess
import wave
from pathlib import Path


class AppError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


class MediaService:
    def __init__(self, settings):
        self.settings = settings

    def run(self, args):
        try:
            result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                                    timeout=self.settings.ffmpeg_timeout_seconds)
        except FileNotFoundError:
            raise AppError("FFMPEG_MISSING", "ไม่พบ FFmpeg/FFprobe กรุณาติดตั้งและเพิ่มใน PATH", 503)
        except subprocess.TimeoutExpired:
            raise AppError("MEDIA_TIMEOUT", "ตรวจสอบหรือแปลงสื่อเกินเวลาที่กำหนด")
        if result.returncode:
            err = result.stderr.lower()
            code = "UNSUPPORTED_CODEC" if b"decoder" in err or b"codec not found" in err else "INVALID_MEDIA"
            raise AppError(code, "ไม่สามารถอ่านสื่อได้ ไฟล์อาจเสียหรือ codec ไม่รองรับ")
        return result.stdout

    def probe(self, source: Path):
        raw = self.run(["ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
                        "-show_format", "-show_streams", "-of", "json", str(source)])
        try:
            info = json.loads(raw)
            fmt = info.get("format", {})
            allowed = {"wav", "mp3", "mov", "mp4", "m4a", "3gp", "3g2", "mj2",
                       "flac", "ogg", "matroska", "webm", "avi"}
            if not set(fmt.get("format_name", "").split(",")) & allowed:
                raise AppError("UNSUPPORTED_FORMAT", "รองรับเฉพาะไฟล์เสียงและวิดีโอแบบ standalone")
            streams = info.get("streams", [])
            audio = [{k: s[k] for k in ("index", "codec_name", "channels", "sample_rate", "channel_layout") if k in s}
                     | {"language": s.get("tags", {}).get("language")} for s in streams if s.get("codec_type") == "audio"]
            if not audio:
                raise AppError("NO_AUDIO_STREAM", "ไฟล์นี้ไม่มี audio stream สำหรับถอดเสียง")
            duration = float(fmt.get("duration", "nan"))
            if not math.isfinite(duration) or duration <= 0:
                raise AppError("INVALID_DURATION", "ไม่พบระยะเวลาสื่อที่ถูกต้อง")
            if duration > self.settings.max_duration_seconds:
                raise AppError("DURATION_TOO_LONG", "ระยะเวลาสื่อเกินขีดจำกัด")
            return {"format_name": fmt["format_name"], "duration_seconds": duration,
                    "audio_streams": audio, "has_video": any(s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic") for s in streams)}
        except (ValueError, KeyError, TypeError):
            raise AppError("INVALID_MEDIA", "ข้อมูลสื่อไม่ถูกต้อง")

    def extract(self, source: Path, target: Path, index: int):
        self.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-xerror", "-threads", "2",
                  "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", f"0:{index}",
                  "-vn", "-acodec", "pcm_s16le", "-ar", "16000",
                  "-t", str(self.settings.max_duration_seconds + 1), "-fs",
                  str(self.settings.max_duration_seconds * 16000 * 2 * 8 + 4096), str(target)])
        try:
            with wave.open(str(target)) as f:
                duration = f.getnframes() / f.getframerate()
                if duration > self.settings.max_duration_seconds:
                    raise AppError("DURATION_TOO_LONG", "ระยะเวลาเสียงที่ถอดรหัสเกินขีดจำกัด")
                if duration <= 0:
                    raise AppError("INVALID_MEDIA", "ไม่พบข้อมูลเสียงที่ถอดรหัสได้")
        except (wave.Error, EOFError):
            raise AppError("INVALID_MEDIA", "ไม่สามารถถอดรหัสเสียงได้")
        return duration

    def prepare_asr(self, source: Path, target: Path):
        """Filtered copy for the model only (rumble cut + level normalization); playback keeps the original."""
        if not self.settings.asr_audio_filter:
            return source
        self.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-xerror", "-threads", "2",
                  "-protocol_whitelist", "file,pipe", "-i", str(source), "-af", self.settings.asr_audio_filter,
                  "-acodec", "pcm_s16le", "-ar", "16000", str(target)])
        return target
