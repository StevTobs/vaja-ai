import re
import time
from app.models.schemas import Segment

SAMPLE_RATE = 16000


def collapse_repeats(text, threshold):
    """Reduce a phrase looped `threshold`+ times in a row (decoder hallucination) to one copy."""
    if threshold < 2:
        return text
    pattern = re.compile(r"(\S.{0,39}?)(?:[\s.…,]*\1){%d,}" % (threshold - 1))
    # Digits/punctuation repeat legitimately (1,000,000; 555 laughter), so only collapse word loops.
    collapse = lambda m: m.group(1) if any(ch.isalpha() for ch in m.group(1)) else m.group(0)
    return re.sub(r"\s{2,}", " ", pattern.sub(collapse, text)).strip()


def is_hallucination(text, markers):
    """True when a segment contains a phrase the model emits from training-data memory, not the audio."""
    return any(marker in text for marker in markers)


def load_model(settings, name):
    from faster_whisper import WhisperModel
    return WhisperModel(name, device=settings.asr_device, compute_type=settings.asr_compute_type,
                        cpu_threads=settings.asr_cpu_threads, download_root=settings.model_cache_dir,
                        local_files_only=settings.model_local_files_only)


class FasterWhisperEngine:
    def __init__(self, settings):
        if settings.asr_device == "cuda":
            from app.asr.runtime import configure_cuda_runtime
            configure_cuda_runtime()
        self.settings = settings
        self.model = load_model(settings, settings.asr_model)
        self.fallback, self.audio = None, None
        if settings.asr_batch_size > 1:
            from faster_whisper import BatchedInferencePipeline
            self.pipeline = BatchedInferencePipeline(model=self.model)
        else:
            self.pipeline = self.model

    def options(self, language):
        s = self.settings
        options = dict(language=None if language == "auto" else language,
                       vad_filter=s.asr_vad, beam_size=s.asr_beam_size,
                       condition_on_previous_text=False,
                       repetition_penalty=getattr(s, "asr_repetition_penalty", 1.0),
                       no_repeat_ngram_size=getattr(s, "asr_no_repeat_ngram_size", 0),
                       initial_prompt=getattr(s, "asr_initial_prompt", "") or None,
                       hotwords=getattr(s, "asr_hotwords", "") or None,
                       without_timestamps=not getattr(s, "asr_timestamps", True))
        if getattr(s, "asr_chunk_length", 0):
            options["chunk_length"] = s.asr_chunk_length
        if s.asr_batch_size > 1:
            # Batched decoding has no temperature fallback; short chunks/timestamps keep segments short.
            options["batch_size"] = s.asr_batch_size
        return options

    def retranscribe(self, path, start, end, language):
        """Decode one time range with the fallback model (lazy-loaded, shares the device)."""
        if self.fallback is None:
            self.fallback = load_model(self.settings, self.settings.asr_fallback_model)
        if self.audio is None:
            from faster_whisper.audio import decode_audio
            self.audio = decode_audio(path, sampling_rate=SAMPLE_RATE)
        clip = self.audio[int(start * SAMPLE_RATE):int(end * SAMPLE_RATE)]
        segments, _ = self.fallback.transcribe(clip, language=None if language == "auto" else language,
                                               beam_size=self.settings.asr_beam_size, vad_filter=False,
                                               condition_on_previous_text=False,
                                               repetition_penalty=getattr(self.settings, "asr_repetition_penalty", 1.0))
        return " ".join(s.text.strip() for s in segments)

    def clean(self, text, path, start, end, language):
        s = self.settings
        threshold = getattr(s, "asr_collapse_repeats", 0)
        markers = [m.strip() for m in getattr(s, "asr_hallucination_markers", "").split("|") if m.strip()]
        text = collapse_repeats(text.strip(), threshold)
        if is_hallucination(text, markers):
            # Whole segment is unreliable: re-decode its time range, or leave a gap rather than wrong text.
            text = ""
            if getattr(s, "asr_fallback_model", ""):
                retry = collapse_repeats(self.retranscribe(path, start, end, language), threshold)
                text = "" if is_hallucination(retry, markers) else retry
        return text

    def transcribe(self, path, language, on_progress=None):
        self.audio = None  # decoded only if a segment needs the fallback model
        segments, info = self.pipeline.transcribe(path, **self.options(language))
        result = []
        last_report = 0
        furthest = 0.0
        count = 0
        for count, s in enumerate(segments, 1):
            text = self.clean(s.text, path, s.start, s.end, language)
            if text:
                result.append(Segment(id=len(result) + 1, start=s.start, end=s.end, text=text).model_dump())
            furthest = max(furthest, s.end)
            now = time.monotonic()
            if on_progress and (count == 1 or now - last_report >= 1):
                # Original-media timestamps are restored by faster-whisper after VAD.
                on_progress({"processed_seconds": furthest, "segments_completed": len(result)})
                last_report = now
        if on_progress and count:
            on_progress({"processed_seconds": furthest, "segments_completed": len(result)})
        return {"language": info.language, "segments": result, "full_text": "\n".join(s["text"] for s in result)}
