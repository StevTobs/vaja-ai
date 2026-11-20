"""Measure local ASR speed on an authorized sample, without printing transcript text."""
import argparse
import json
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from app.asr.faster_whisper_engine import FasterWhisperEngine
from app.config import Settings
from app.repositories.file_repository import atomic_json
from app.services.media_service import MediaService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings(asr_device=args.device, asr_compute_type="float16" if args.device == "cuda" else "int8",
                        asr_beam_size=args.beam_size, asr_batch_size=args.batch_size)
    media = MediaService(settings)
    probe = media.probe(args.source.resolve())
    print("Preparing local audio sample...", flush=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="asr-bench-", dir=args.report.parent) as directory:
        audio = Path(directory).resolve() / "sample.wav"
        start = time.perf_counter()
        media.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-protocol_whitelist", "file,pipe",
                   "-i", str(args.source.resolve()), "-map", f"0:{probe['audio_streams'][0]['index']}",
                   "-vn", "-t", str(max(1, args.seconds)), "-c:a", "pcm_s16le", "-ar", "16000", str(audio)])
        extract_seconds = time.perf_counter() - start
        with wave.open(str(audio)) as wav:
            duration = wav.getnframes() / wav.getframerate()
        print(f"Sample ready: {duration:.1f}s; loading model on {settings.asr_device}...", flush=True)
        start = time.perf_counter()
        engine = FasterWhisperEngine(settings)
        load_seconds = time.perf_counter() - start
        print(f"Model loaded in {load_seconds:.2f}s; transcribing...", flush=True)
        start = time.perf_counter()
        result = engine.transcribe(str(audio), settings.asr_language)
        elapsed = time.perf_counter() - start
        report = dict(device=settings.asr_device, compute_type=settings.asr_compute_type,
                      model=settings.asr_model, beam_size=settings.asr_beam_size, batch_size=settings.asr_batch_size,
                      source_duration_seconds=probe["duration_seconds"], sample_seconds=duration,
                      extract_seconds=round(extract_seconds, 3), model_load_seconds=round(load_seconds, 3),
                      transcribe_seconds=round(elapsed, 3), real_time_factor=round(elapsed / duration, 4),
                      segment_count=len(result["segments"]))
        atomic_json(args.report.resolve(), report)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
