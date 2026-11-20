"""Download model weights only; this script never opens user media."""
from app.config import get_settings


def main():
    from faster_whisper.utils import download_model
    from app.services.diarization_service import DiarizationService
    settings = get_settings()
    for name in filter(None, (settings.asr_model, settings.asr_fallback_model)):
        path = download_model(name, cache_dir=settings.model_cache_dir)
        print(f"Model ready: {path}")
    if settings.diarization_enabled:
        diarization = DiarizationService(settings)
        if not diarization.ready():
            diarization.download()
        print(f"Speaker model ready: {diarization.directory}")


if __name__ == "__main__":
    main()
