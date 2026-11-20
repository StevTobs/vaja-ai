import signal
import threading
from filelock import Timeout
from app.config import get_settings
from worker.processor import Worker


def main():
    worker = Worker(get_settings())
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        with worker.repo.lock("worker", timeout=0):
            worker.recover()
            # Independent heartbeat also covers blocking FFmpeg calls.
            def pulse():
                while not stop.wait(3):
                    worker.heartbeat()
            thread = threading.Thread(target=pulse, daemon=True)
            thread.start()
            try:
                while not stop.is_set():
                    worker.heartbeat()
                    if not worker.process_next():
                        stop.wait(worker.settings.job_poll_seconds)
            finally:
                stop.set()
                thread.join(5)
                worker.engine.close()
                (worker.repo.data_dir / "worker.json").unlink(missing_ok=True)
    except Timeout:
        raise SystemExit("Another worker owns this data directory; only one worker is supported.")


if __name__ == "__main__":
    main()
