import csv
import io
import json
from app.repositories.file_repository import utcnow
from app.services.media_service import AppError


def timestamp(seconds, separator=","):
    millis = round(seconds * 1000)
    hours, millis = divmod(millis, 3600000)
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}"


def cell(value):
    # Spreadsheets run cells starting with these as formulas (CSV injection).
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def csv_export(segments, speaker):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(["ลำดับ", "เวลาเริ่ม", "เวลาจบ", "เริ่ม (วินาที)", "จบ (วินาที)", "ผู้พูด", "ข้อความ"])
    for i, s in enumerate(segments, 1):
        writer.writerow([i, timestamp(s["start"], "."), timestamp(s["end"], "."), f"{s['start']:.3f}",
                         f"{s['end']:.3f}", cell(speaker(s)), cell(s["text"])])
    # BOM so Excel opens Thai text as UTF-8.
    return "﻿" + out.getvalue()


def speaker_labels(segments, names):
    """Names for every label used, keeping given names and filling defaults (ผู้พูด N)."""
    names = dict(names or {})
    for s in segments:
        label = s.get("speaker")
        if label and label not in names:
            names[label] = f"ผู้พูด {label[1:]}"
    return names


class TranscriptService:
    def __init__(self, repo):
        self.repo = repo

    def get(self, job_id):
        job = self.repo.load_manifest(job_id)
        if job["status"] != "succeeded":
            raise AppError("NOT_READY", "ผลถอดเสียงยังไม่พร้อม", 409)
        original = self.repo.load_json(job_id, "transcript.original.json")
        try:
            edited = self.repo.load_json(job_id, "transcript.edited.json")
        except FileNotFoundError:
            edited = None
        # A crash between immutable revision and latest-pointer writes is recoverable.
        revisions = list(self.repo.job_dir(job_id).glob("transcript.revision.*.json"))
        if revisions:
            latest = max(revisions, key=lambda p: int(p.name.split(".")[2]))
            if edited is None or int(latest.name.split(".")[2]) > edited["revision"]:
                edited = self.repo.load_json(job_id, latest.name)
        return {"original": original, "edited": edited, "revision": edited["revision"] if edited else 0}

    def save(self, job_id, edit):
        with self.repo.lock():
            state = self.get(job_id)
            if edit.revision != state["revision"]:
                raise AppError("REVISION_CONFLICT", "มีการแก้ไขจากหน้าต่างอื่น กรุณาโหลดผลใหม่", 409)
            original = state["original"]
            current = state["edited"] or original
            segments = original["segments"] if edit.reset else [s.model_dump() for s in edit.segments]
            # Edits change text and speaker only; timing and segment identities remain measured ASR data.
            if [(s["id"], s["start"], s["end"]) for s in segments] != [(s["id"], s["start"], s["end"]) for s in original["segments"]]:
                raise AppError("INVALID_SEGMENTS", "ต้องคง segment และเวลาจาก AI ต้นฉบับ")
            if edit.reset:
                names = original.get("speaker_names")
            elif edit.speaker_names is not None:
                names = {k: v.strip() for k, v in edit.speaker_names.items()}
            else:
                names = current.get("speaker_names")
            names = speaker_labels(segments, names)
            doc = {**original, "segments": segments, "speaker_names": names,
                   "full_text": "\n".join(s["text"] for s in segments),
                   "revision": state["revision"] + 1, "edited_at": utcnow()}
            # Immutable revision files remain available after subsequent saves/reset.
            self.repo.save_json(job_id, f"transcript.revision.{doc['revision']}.json", doc)
            self.repo.save_json(job_id, "transcript.edited.json", doc)
            return doc

    def export(self, job_id, fmt, version):
        with self.repo.lock():
            state = self.get(job_id)
            doc = state["original"] if version == "original" else state["edited"] or state["original"]
            job = self.repo.load_manifest(job_id)
        if fmt == "json":
            return json.dumps({"metadata": job, "transcript": doc}, ensure_ascii=False, indent=2), "application/json"
        names = doc.get("speaker_names") or {}
        speaker = lambda s: names.get(s.get("speaker"), s.get("speaker") or "")  # noqa: E731
        has_speakers = any(s.get("speaker") for s in doc["segments"])
        if fmt == "csv":
            return csv_export(doc["segments"], speaker), "text/csv"
        if fmt == "txt":
            if not has_speakers:
                return doc["full_text"] + "\n", "text/plain"
            return "".join(f"{speaker(s)}: {s['text']}\n" for s in doc["segments"]), "text/plain"
        sep = "." if fmt == "vtt" else ","
        lines = ["WEBVTT\n"] if fmt == "vtt" else []
        for i, s in enumerate(doc["segments"], 1):
            text = s["text"].replace("\r", " ").replace("\n", " ").replace("-->", "→")
            who = speaker(s).replace("<", "").replace(">", "").replace("-->", "→")
            if who:
                text = f"<v {who}>{text}" if fmt == "vtt" else f"{who}: {text}"
            lines.append(f"{i}\n{timestamp(s['start'], sep)} --> {timestamp(s['end'], sep)}\n{text}\n")
        return "\n".join(lines), "text/vtt" if fmt == "vtt" else "application/x-subrip"
