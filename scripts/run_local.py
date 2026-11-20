"""Run API and singleton worker together; Ctrl+C stops both."""
import subprocess
import os
import sys
import time
from app.config import get_settings


def main():
    cfg = get_settings()
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", cfg.host,
                            "--port", str(cfg.port), "--no-access-log"])
    worker = subprocess.Popen([sys.executable, "-m", "worker.main"])
    try:
        print(f"VAJA AI: http://{cfg.host}:{cfg.port} (Ctrl+C to stop)")
        while api.poll() is None and worker.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in (api, worker):
            if process.poll() is None:
                if os.name == "nt":
                    # Windows venv python is a redirector; terminate its child tree too.
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    process.terminate()
        for process in (api, worker):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
