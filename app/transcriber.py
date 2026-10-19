"""Local transcription with faster-whisper. Runs on an NVIDIA GPU when there is one, on the CPU otherwise.

`setup_environment()` must run before `faster_whisper` is imported anywhere: the CUDA DLLs (cuBLAS,
cuDNN) are found through PATH, and `os.add_dll_directory` alone is not enough for CTranslate2.

The model is downloaded once, on the first run, into `modelo/` next to the app. After that the app works
offline: nothing goes to the internet, not even a version check.
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "modelo"
MODEL = os.environ.get("DITADO_MODELO", "large-v3-turbo")
LANGUAGE = os.environ.get("DITADO_IDIOMA", "pt")


def _model_cached():
    return any(MODEL_DIR.glob(f"hub/models--*--faster-whisper-{MODEL}/snapshots/*/model.bin")) or \
        any(MODEL_DIR.glob(f"hub/models--*--whisper-{MODEL}*/snapshots/*/model.bin"))


def setup_environment():
    os.environ.setdefault("HF_HOME", str(MODEL_DIR))
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    if _model_cached():
        os.environ["HF_HUB_OFFLINE"] = "1"  # already downloaded: never touch the network again
    dll_dirs = []
    try:  # only installed on machines with an NVIDIA card (see instalar.bat)
        import nvidia.cublas
        import nvidia.cudnn
        dll_dirs = [str(Path(list(m.__path__)[0]) / "bin") for m in (nvidia.cublas, nvidia.cudnn)]
    except ImportError:
        pass
    current = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p and p not in dll_dirs]
    os.environ["PATH"] = os.pathsep.join(dll_dirs + current)
    for d in dll_dirs:
        if os.path.isdir(d) and sys.platform == "win32":
            os.add_dll_directory(d)
    return dll_dirs


def pick_device():
    forced = os.environ.get("DITADO_DISPOSITIVO")
    if forced:
        return forced, ("float16" if forced == "cuda" else "int8")
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


class Transcriber:
    def __init__(self, model=MODEL, language=LANGUAGE):
        from faster_whisper import WhisperModel
        self.device, compute_type = pick_device()
        t = time.perf_counter()
        offline = os.environ.get("HF_HUB_OFFLINE") == "1"
        try:
            self.model = WhisperModel(model, device=self.device, compute_type=compute_type, local_files_only=offline)
        except Exception:
            if self.device != "cuda":
                raise
            # CUDA present but the libraries are not: fall back to the CPU instead of not starting at all.
            self.device, compute_type = "cpu", "int8"
            self.model = WhisperModel(model, device="cpu", compute_type="int8", local_files_only=offline)
        self.load_seconds = time.perf_counter() - t
        self.language = language

    def warmup(self):
        import numpy as np
        self.transcribe(np.zeros(16000, dtype=np.float32), vad=False)

    def transcribe(self, audio, vad=True):
        """audio: float32 mono 16 kHz (numpy) or a file path. Returns (text, seconds)."""
        t = time.perf_counter()
        segments, _ = self.model.transcribe(
            audio, language=self.language, task="transcribe", beam_size=5,
            vad_filter=vad, vad_parameters={"min_silence_duration_ms": 500},
            # Timestamps on: without them, a dictation longer than 30 s loses whole sentences at the window
            # seams (measured: up to 22% of the words missing on 70 s of speech, 0% with timestamps, +0.25 s).
            condition_on_previous_text=False, without_timestamps=False)
        text = " ".join(s.text.strip() for s in segments).strip()
        return text, time.perf_counter() - t
