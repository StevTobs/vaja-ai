"""Speaker diarization from the voice (who spoke when), fully local on CPU.

Uses sherpa-onnx with the pyannote segmentation-3.0 model and the NeMo TitaNet-small voice
embedding model (~45 MB total, downloaded once into MODEL_CACHE_DIR/diarization). Labels are
neutral (S1, S2, ...); roles such as agent / customer come from the optional AI analysis.
"""
import shutil
import tarfile
import tempfile
import urllib.request
import wave
from pathlib import Path

import numpy as np

from app.services.media_service import AppError

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SEGMENTATION_URL = f"{RELEASES}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
EMBEDDING_URL = f"{RELEASES}/speaker-recongition-models/nemo_en_titanet_small.onnx"
SAMPLE_RATE = 16000


def default_name(label):
    return f"ผู้พูด {label.removeprefix('S')}"


def assign_speakers(segments, turns):
    """Give each ASR segment the speaker who talks most inside it (nearest turn if none overlap)."""
    out = []
    for s in segments:
        overlap = {}
        for t in turns:
            o = min(s["end"], t["end"]) - max(s["start"], t["start"])
            if o > 0:
                overlap[t["speaker"]] = overlap.get(t["speaker"], 0) + o
        if overlap:
            speaker = max(overlap, key=overlap.get)
        elif turns:
            mid = (s["start"] + s["end"]) / 2
            speaker = min(turns, key=lambda t: min(abs(t["start"] - mid), abs(t["end"] - mid)))["speaker"]
        else:
            speaker = None
        out.append({**s, "speaker": speaker})
    return out


def read_mono(path):
    with wave.open(str(path)) as f:
        if f.getsampwidth() != 2:
            raise AppError("DIARIZATION_AUDIO", "รูปแบบเสียงไม่รองรับการแยกผู้พูด")
        rate, channels = f.getframerate(), f.getnchannels()
        data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != SAMPLE_RATE:
        raise AppError("DIARIZATION_AUDIO", "ต้องเป็นเสียง 16 kHz สำหรับการแยกผู้พูด")
    return data


class DiarizationService:
    def __init__(self, settings):
        self.settings = settings

    @property
    def directory(self):
        return Path(self.settings.model_cache_dir).resolve() / "diarization"

    @property
    def segmentation_model(self):
        return self.directory / "sherpa-onnx-pyannote-segmentation-3-0" / "model.onnx"

    @property
    def embedding_model(self):
        return self.directory / EMBEDDING_URL.rsplit("/", 1)[1]

    def ready(self):
        return self.segmentation_model.is_file() and self.embedding_model.is_file()

    def download(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            archive = Path(tmp) / "segmentation.tar.bz2"
            with urllib.request.urlopen(SEGMENTATION_URL, timeout=120) as r, archive.open("wb") as f:
                shutil.copyfileobj(r, f)
            with tarfile.open(archive) as tar:
                tar.extractall(self.directory, filter="data")
            target = self.embedding_model
            partial = target.with_suffix(".part")
            with urllib.request.urlopen(EMBEDDING_URL, timeout=120) as r, partial.open("wb") as f:
                shutil.copyfileobj(r, f)
            partial.replace(target)
        if not self.ready():
            raise AppError("DIARIZATION_DOWNLOAD", "ดาวน์โหลดโมเดลแยกผู้พูดไม่ครบ", 502)

    def run(self, wav_path, progress=None):
        """Return speaker turns [{start, end, speaker: 'S1'}...] sorted by time."""
        if not self.ready():
            raise AppError("DIARIZATION_MODEL_MISSING", "ยังไม่ได้ดาวน์โหลดโมเดลแยกผู้พูด (หน้า ตั้งค่า)", 409)
        import sherpa_onnx
        s = self.settings
        threads = max(1, s.asr_cpu_threads)
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(self.segmentation_model)),
                num_threads=threads),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(self.embedding_model), num_threads=threads),
            clustering=sherpa_onnx.FastClusteringConfig(
                num_clusters=s.diarization_num_speakers if s.diarization_num_speakers > 0 else -1,
                threshold=s.diarization_threshold),
            min_duration_on=0.3, min_duration_off=0.5)
        engine = sherpa_onnx.OfflineSpeakerDiarization(config)
        samples = read_mono(wav_path)

        def callback(done, total):
            if progress:
                progress(done, total)
            return 0
        result = engine.process(samples, callback=callback).sort_by_start_time()
        # Number speakers by first appearance so S1 is whoever talks first.
        order = {}
        turns = []
        for seg in result:
            label = order.setdefault(seg.speaker, f"S{len(order) + 1}")
            turns.append({"start": round(seg.start, 3), "end": round(seg.end, 3), "speaker": label})
        return turns

    def label(self, wav_path, segments, progress=None):
        """Segments with a `speaker` field plus default speaker names."""
        turns = self.run(wav_path, progress)
        labelled = assign_speakers(segments, turns)
        names = {label: default_name(label) for label in sorted({s["speaker"] for s in labelled if s["speaker"]},
                                                                 key=lambda x: int(x[1:]))}
        return labelled, names


class SpeakerJobs:
    """Run diarization for an already-transcribed job in the API process; the result is a new revision."""

    def __init__(self, repo, transcripts, settings):
        self.repo, self.transcripts, self.diarization = repo, transcripts, DiarizationService(settings)

    def get(self, job_id):
        self.repo.load_manifest(job_id)
        try:
            return self.repo.load_json(job_id, "speakers.json")
        except FileNotFoundError:
            return {"status": "none"}

    def start(self, job_id):
        import threading
        from filelock import Timeout
        from app.repositories.file_repository import utcnow
        if not self.diarization.ready():
            raise AppError("DIARIZATION_MODEL_MISSING", "ยังไม่ได้ดาวน์โหลดโมเดลแยกผู้พูด (หน้า ตั้งค่า)", 409)
        lock = self.repo.lock(f"speakers-{job_id}", timeout=0)
        try:
            lock.acquire()
        except Timeout:
            raise AppError("DIARIZATION_RUNNING", "กำลังแยกผู้พูดงานนี้อยู่", 409)
        try:
            with self.repo.lock():
                self.transcripts.get(job_id)  # must be a finished transcript
                record = {"status": "running", "started_at": utcnow(), "finished_at": None, "error_code": None,
                          "error_message": None, "progress": 0}
                self.repo.save_json(job_id, "speakers.json", record)
            threading.Thread(target=self._run, args=(job_id, dict(record), lock), daemon=True).start()
            return record
        except BaseException:
            lock.release()
            raise

    def _run(self, job_id, record, lock):
        from app.models.schemas import EditTranscript
        from app.repositories.file_repository import utcnow
        try:
            try:
                turns = self.diarization.run(self.repo.path(job_id, "playback.wav"))
                for _ in range(3):  # re-read if the transcript was edited meanwhile
                    state = self.transcripts.get(job_id)
                    source = state["edited"] or state["original"]
                    labelled = assign_speakers(source["segments"], turns)
                    names = {k: v for k, v in (source.get("speaker_names") or {}).items()}
                    try:
                        doc = self.transcripts.save(job_id, EditTranscript(
                            revision=state["revision"], segments=labelled, speaker_names=names))
                        break
                    except AppError as e:
                        if e.code != "REVISION_CONFLICT":
                            raise
                else:
                    raise AppError("REVISION_CONFLICT", "ข้อความถูกแก้ไขระหว่างแยกผู้พูด กรุณาลองใหม่", 409)
                record.update(status="succeeded", revision=doc["revision"],
                              speakers=len(doc.get("speaker_names") or {}))
            except AppError as e:
                record.update(status="failed", error_code=e.code, error_message=e.message)
            except Exception:
                record.update(status="failed", error_code="DIARIZATION_FAILED", error_message="แยกผู้พูดไม่สำเร็จ")
            record["finished_at"] = utcnow()
            with self.repo.lock():
                try:
                    job = self.repo.load_manifest(job_id)
                except (FileNotFoundError, ValueError):
                    return
                if not job.get("delete_requested"):
                    self.repo.save_json(job_id, "speakers.json", record)
        finally:
            lock.release()
