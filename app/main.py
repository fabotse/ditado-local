"""Ditado local: hold the right Alt (AltGr), speak, release; the text lands where the cursor is.

    python app/main.py [--sair-apos SEGUNDOS]
"""
import argparse
import ctypes
import logging
import queue
import sys
import threading
import time
from ctypes import wintypes as w
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from transcriber import setup_environment  # noqa: E402  (must run before faster_whisper loads)

setup_environment()

from clipboard import ClipboardPaster  # noqa: E402
from hotkey import OWN_INPUT_TAG, KeyboardHook  # noqa: E402
from indicator import BUSY, HIDDEN, MESSAGE, RECORDING, Indicator  # noqa: E402
from win32 import (ERROR_ALREADY_EXISTS, VK_LCONTROL, VK_LMENU, VK_LSHIFT, VK_LWIN, VK_MASK, VK_RCONTROL,  # noqa: E402
                   VK_RMENU, VK_RSHIFT, VK_RWIN, kernel32, key_input, key_is_down, send_inputs, user32)

log = logging.getLogger("ditado")

MIN_AUDIO_SECONDS = 0.3
SILENCE_RMS = 0.0015
_MODIFIERS = (VK_LCONTROL, VK_RCONTROL, VK_LMENU, VK_RMENU, VK_LSHIFT, VK_RSHIFT, VK_LWIN, VK_RWIN)


def wait_modifiers_released(timeout=120.0):
    """Ctrl+V must not mix with a key the user still holds (AltGr+Ctrl+V is not a paste)."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not any(key_is_down(vk) for vk in _MODIFIERS):
            return True
        time.sleep(0.02)
    return False


def send_menu_mask():
    """An unassigned key while Alt is held, so releasing Alt alone never opens a menu bar."""
    send_inputs([key_input(VK_MASK, extra=OWN_INPUT_TAG), key_input(VK_MASK, up=True, extra=OWN_INPUT_TAG)])


class DictationApp:
    """Wires hook -> recorder -> transcriber -> paster. Every part can be swapped for tests."""

    def __init__(self, transcriber, recorder, paster, indicator=None):
        self.transcriber = transcriber
        self.recorder = recorder
        self.paster = paster
        self.indicator = indicator
        self.hook = KeyboardHook(self.on_hotkey)
        self.jobs = queue.Queue()
        self.results = queue.Queue()  # (text, PasteResult) per dictation, for tests and the log
        self._worker = threading.Thread(target=self._work, name="transcribe", daemon=True)
        self._busy = 0
        self._busy_lock = threading.Lock()

    def start(self):
        self._worker.start()
        self.hook.start()

    def stop(self):
        self.hook.stop()
        if self.recorder.recording:
            self.recorder.stop()
        self.jobs.put(None)
        self._worker.join(10)

    def _show(self, state, message=""):
        if self.indicator:
            self.indicator.set(state, message)

    # Called on the hook's dispatch thread, never inside the hook callback itself.
    def on_hotkey(self, event, t):
        if event == "start":
            send_menu_mask()
            try:
                self.recorder.start()
            except Exception as e:
                log.error("microfone indisponivel: %s", e)
                self._show(MESSAGE, "Microfone indisponivel")
                return
            self._show(RECORDING)
            log.info("gravando (microfone abriu em %.0f ms)", (self.recorder.open_latency or 0) * 1000)
        elif event == "cancel":
            if self.recorder.recording:
                self.recorder.stop()
            self._show(BUSY if self._busy else HIDDEN)
        elif event == "release":
            if not self.recorder.recording:
                return
            audio = self.recorder.stop()
            with self._busy_lock:
                self._busy += 1
            self._show(BUSY)
            self.jobs.put(audio)

    def _work(self):
        while True:
            audio = self.jobs.get()
            if audio is None:
                return
            try:
                self._handle(audio)
            except Exception:
                log.exception("falha no ditado")
                self._show(MESSAGE, "Falha no ditado")
            finally:
                with self._busy_lock:
                    self._busy -= 1
                if not self._busy and not self.recorder.recording and self.indicator \
                        and self.indicator.state == BUSY:
                    self._show(HIDDEN)

    def _handle(self, audio):
        seconds = len(audio) / 16000
        if seconds < MIN_AUDIO_SECONDS or float((audio ** 2).mean() ** 0.5) < SILENCE_RMS:
            log.info("audio curto ou silencioso (%.1f s), ignorado", seconds)
            self.results.put(("", None))
            return
        text, took = self.transcriber.transcribe(audio)
        log.info("transcrito: %.1f s de audio em %.2f s, %d caracteres", seconds, took, len(text))
        if not text:
            self.results.put(("", None))
            return
        wait_modifiers_released()
        result = self.paster.paste(text)
        log.info("colagem: %s", result)
        if result.kept:
            self._show(MESSAGE, "Copiado. Cole com Ctrl+V")
        elif result.error:
            self._show(MESSAGE, "Nao consegui colar")
        self.results.put((text, result))


def single_instance():
    handle = kernel32.CreateMutexW(None, False, "Local\\DitadoLocal")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        return None
    return handle


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ditado local por voz (segure o Alt da direita)")
    parser.add_argument("--sair-apos", type=float, default=0, help="encerra sozinho depois de N segundos (teste)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        user32.SetProcessDpiAwarenessContext(w.HANDLE(-4))
    except Exception:
        pass
    if not single_instance():
        log.error("o ditado ja esta rodando")
        return 2

    from recorder import Recorder
    from transcriber import MODEL, Transcriber

    recorder = Recorder()
    indicator = Indicator(level_source=lambda: recorder.level)
    indicator.start()
    indicator.set(MESSAGE, "Carregando modelo...", seconds=120)
    transcriber = Transcriber()
    transcriber.warmup()
    log.info("modelo %s carregado na %s em %.1f s", MODEL, transcriber.device, transcriber.load_seconds)
    paster = ClipboardPaster()
    paster.start()
    app = DictationApp(transcriber, recorder, paster, indicator)
    app.start()
    indicator.set(MESSAGE, "Pronto: segure o Alt da direita", seconds=2.5)
    log.info("pronto. Segure o Alt da direita (AltGr) e fale. Ctrl+C ou feche esta janela para sair.")

    deadline = time.monotonic() + args.sair_apos if args.sair_apos else None
    try:
        while deadline is None or time.monotonic() < deadline:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    log.info("encerrando")
    app.stop()
    paster.stop()
    indicator.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
