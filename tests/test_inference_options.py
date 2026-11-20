from types import SimpleNamespace
import pytest
from app.asr.faster_whisper_engine import FasterWhisperEngine


@pytest.mark.parametrize("batch_size", [1, 8])
def test_beam_and_batch_settings_are_forwarded(batch_size):
    class Pipeline:
        def transcribe(self, path, **options):
            self.options = options
            return iter([]), SimpleNamespace(language="th")
    engine = FasterWhisperEngine.__new__(FasterWhisperEngine)
    engine.settings = SimpleNamespace(asr_vad=True, asr_beam_size=1, asr_batch_size=batch_size)
    engine.pipeline = Pipeline()
    engine.transcribe("unused.wav", "th")
    assert engine.pipeline.options["beam_size"] == 1
    assert engine.pipeline.options["language"] == "th"
    assert engine.pipeline.options.get("batch_size", 1) == batch_size


def test_batched_keeps_timestamps_and_vocabulary_hints():
    engine = FasterWhisperEngine.__new__(FasterWhisperEngine)
    engine.settings = SimpleNamespace(asr_vad=True, asr_beam_size=5, asr_batch_size=8, asr_repetition_penalty=1.1,
                                      asr_no_repeat_ngram_size=0, asr_initial_prompt="ค่าไฟ มิเตอร์", asr_hotwords="")
    options = engine.options("th")
    assert options["without_timestamps"] is False
    assert options["repetition_penalty"] == 1.1
    assert options["initial_prompt"] == "ค่าไฟ มิเตอร์"
    assert options["hotwords"] is None


@pytest.mark.parametrize("text,expected", [
    ("สวัสดีครับ สวัสดีครับ สวัสดีครับ สวัสดีครับสวัสดีครับ", "สวัสดีครับ"),
    ("คือ...คือ...คือ...คือ...คือ...", "คือ..."),
    ("ไม่เกิน ไม่เกิน 5,000 ครับ", "ไม่เกิน ไม่เกิน 5,000 ครับ"),
    ("1,000,000 บาท 55555", "1,000,000 บาท 55555"),
])
def test_collapse_repeated_hallucination(text, expected):
    from app.asr.faster_whisper_engine import collapse_repeats
    assert collapse_repeats(text, 4) == expected


def test_loop_only_segments_are_collapsed_and_renumbered():
    class Pipeline:
        def transcribe(self, path, **options):
            segs = [SimpleNamespace(start=0, end=1, text=" ค่อย ค่อย ค่อย ค่อย ค่อย"), SimpleNamespace(start=1, end=2, text="  "),
                    SimpleNamespace(start=2, end=3, text=" ค่าไฟ")]
            return iter(segs), SimpleNamespace(language="th")
    engine = FasterWhisperEngine.__new__(FasterWhisperEngine)
    engine.settings = SimpleNamespace(asr_vad=True, asr_beam_size=5, asr_batch_size=1, asr_collapse_repeats=4)
    engine.pipeline = Pipeline()
    result = engine.transcribe("unused.wav", "th")
    assert [(s["id"], s["text"]) for s in result["segments"]] == [(1, "ค่อย"), (2, "ค่าไฟ")]


def test_hallucinated_segment_is_redecoded_or_left_out():
    class Pipeline:
        def transcribe(self, path, **options):
            segs = [SimpleNamespace(start=0, end=5, text="ค่าไฟ วิเคราะห์บอล บอลเต็ง"), SimpleNamespace(start=5, end=9, text="ใบแจ้งหนี้")]
            return iter(segs), SimpleNamespace(language="th")
    engine = FasterWhisperEngine.__new__(FasterWhisperEngine)
    engine.settings = SimpleNamespace(asr_vad=True, asr_beam_size=5, asr_batch_size=8, asr_collapse_repeats=4,
                                      asr_hallucination_markers="บอลเต็ง|A-TECHงานเลี้ยง", asr_fallback_model="")
    engine.pipeline = Pipeline()
    assert [s["text"] for s in engine.transcribe("unused.wav", "th")["segments"]] == ["ใบแจ้งหนี้"]
    engine.settings.asr_fallback_model = "turbo"
    calls = []
    engine.retranscribe = lambda path, start, end, language: calls.append((start, end)) or "ค่าไฟแพงมาก"
    result = engine.transcribe("unused.wav", "th")
    assert calls == [(0, 5)]
    assert [(s["start"], s["text"]) for s in result["segments"]] == [(0, "ค่าไฟแพงมาก"), (5, "ใบแจ้งหนี้")]


def test_asr_copy_is_filtered_but_playback_is_untouched(tmp_path, media_tools):
    from app.config import Settings
    from app.services.media_service import MediaService
    from tests.conftest import ffmpeg
    source = tmp_path / "audio.wav"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-ar", "16000", source)
    before = source.read_bytes()
    media = MediaService(Settings(_env_file=None))
    target = media.prepare_asr(source, tmp_path / "asr.wav")
    assert target != source and target.exists() and source.read_bytes() == before
    assert MediaService(Settings(_env_file=None, asr_audio_filter="")).prepare_asr(source, tmp_path / "x.wav") == source
