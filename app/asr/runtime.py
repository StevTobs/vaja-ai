"""Discover optional NVIDIA wheels without modifying the machine's global PATH."""
import os
import sysconfig
from pathlib import Path

_dll_handles = []


def configure_cuda_runtime():
    if os.name != "nt":
        return
    root = Path(sysconfig.get_path("purelib")) / "nvidia"
    directories = [root / package / "bin" for package in ("cublas", "cudnn", "cuda_nvrtc")]
    for directory in directories:
        if directory.is_dir():
            _dll_handles.append(os.add_dll_directory(str(directory)))
            os.environ["PATH"] = str(directory) + os.pathsep + os.environ.get("PATH", "")
