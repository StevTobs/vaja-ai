"""Desktop launcher (no console): start API + worker in the background and open the browser.

Used by the desktop / Start Menu shortcuts that the installer creates:
    pythonw -m scripts.launch          start (or just open the browser if already running)
    pythonw -m scripts.launch --stop   stop a running copy

The "ปิดโปรแกรม" button in the web UI writes the same stop flag this launcher watches.
Logs: data/logs/api.log and data/logs/worker.log.
"""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from filelock import FileLock, Timeout

from app.config import get_settings

ROOT = Path(__file__).resolve().parent.parent
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def healthy(url):
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


def console_python():
    # pythonw has no stdout; children get python.exe so their logs work, without a window.
    exe = Path(sys.executable)
    candidate = exe.with_name("python.exe") if exe.name.lower() == "pythonw.exe" else exe
    return str(candidate if candidate.exists() else exe)


def kill(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=False, creationflags=NO_WINDOW)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def main():
    cfg = get_settings()
    data = Path(cfg.data_dir).resolve()
    (data / "locks").mkdir(parents=True, exist_ok=True)
    stop_flag = data / "stop.flag"
    host = "127.0.0.1" if cfg.host in ("0.0.0.0", "::") else cfg.host
    url = f"http://{host}:{cfg.port}"

    if "--stop" in sys.argv:
        stop_flag.write_text("stop", encoding="utf-8")
        return

    lock = FileLock(str(data / "locks" / "launcher.lock"), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        webbrowser.open(url)  # already running
        return
    try:
        stop_flag.unlink(missing_ok=True)
        logs = data / "logs"
        logs.mkdir(exist_ok=True)
        env = {**os.environ, "VAJA_LAUNCHER": "1", "PYTHONIOENCODING": "utf-8"}
        commands = {
            "api": [console_python(), "-m", "uvicorn", "app.main:app", "--host", cfg.host,
                    "--port", str(cfg.port), "--no-access-log"],
            "worker": [console_python(), "-m", "worker.main"],
        }
        processes, restarts = {}, []

        def start(name):
            log = open(logs / f"{name}.log", "ab")
            processes[name] = subprocess.Popen(commands[name], cwd=ROOT, env=env, stdout=log, stderr=log,
                                               stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)

        for name in commands:
            start(name)
        for _ in range(120):
            if healthy(url):
                if os.environ.get("VAJA_NO_BROWSER") != "1":
                    webbrowser.open(url)
                break
            if processes["api"].poll() is not None:
                return  # port in use or bad config; see data/logs/api.log
            time.sleep(0.5)
        while not stop_flag.exists():
            time.sleep(1)
            for name, process in list(processes.items()):
                if process.poll() is not None:
                    now = time.monotonic()
                    restarts[:] = [t for t in restarts if now - t < 60] + [now]
                    if len(restarts) > 5:
                        return  # crash loop; logs explain why
                    start(name)
    finally:
        for process in locals().get("processes", {}).values():
            kill(process)
        stop_flag.unlink(missing_ok=True)
        lock.release()


if __name__ == "__main__":
    main()
