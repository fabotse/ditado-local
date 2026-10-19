"""Microphone capture: the default input device, opened only while the key is held."""
import threading
import time

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
MAX_SECONDS = 300  # a stuck key cannot fill the memory


class Recorder:
    def __init__(self, samplerate=SAMPLE_RATE):
        self.samplerate = samplerate
        self._chunks = []
        self._stream = None
        self._lock = threading.Lock()
        self._frames = 0
        self.level = 0.0  # last chunk RMS, 0..1, read by the indicator
        self.open_latency = None

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            if self._frames >= MAX_SECONDS * self.samplerate:
                return
            self._chunks.append(indata[:, 0].copy())
            self._frames += frames
        self.level = float(np.sqrt(np.mean(indata[:, 0] ** 2)))

    def start(self):
        with self._lock:
            self._chunks, self._frames = [], 0
        t = time.perf_counter()
        try:
            self._stream = sd.InputStream(samplerate=self.samplerate, channels=1, dtype="float32",
                                          callback=self._callback, blocksize=0, latency="low")
        except sd.PortAudioError:
            # Some drivers refuse 16 kHz: record at the device's own rate and resample in stop().
            rate = int(sd.query_devices(kind="input")["default_samplerate"])
            self._stream = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                          callback=self._callback, blocksize=0, latency="low")
        self._stream.start()
        self.open_latency = time.perf_counter() - t

    def stop(self):
        """Close the device and return the audio as float32 mono at 16 kHz."""
        stream, self._stream = self._stream, None
        rate = int(stream.samplerate) if stream is not None else self.samplerate
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        self.level = 0.0
        with self._lock:
            chunks, self._chunks = self._chunks, []
        audio = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        if rate != self.samplerate and audio.size:
            n = int(audio.size * self.samplerate / rate)
            audio = np.interp(np.linspace(0, audio.size - 1, n), np.arange(audio.size), audio).astype(np.float32)
        return audio

    @property
    def recording(self):
        return self._stream is not None
