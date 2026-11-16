"""
Thin wrapper around Coqui TTS's XTTS v2 model.

XTTS v2 does zero-shot voice cloning: give it a few seconds of reference
audio and a sentence of text, and it generates new speech in that voice.
Loading the model is slow (several seconds to a couple of minutes, mostly
GPU/CPU dependent) and memory-heavy, so we load it once, lazily, and reuse
it across requests.
"""

import threading


class VoiceEngine:
    def __init__(self):
        self._model = None
        self._lock = threading.Lock()

    def is_loaded(self) -> bool:
        return self._model is not None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:  # re-check after acquiring the lock
                return
            # Imported here so the web server can boot instantly and only
            # pays the (large) import + model-download cost on first use.
            from TTS.api import TTS
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

    def synthesize(
        self,
        text: str,
        speaker_wav: str,
        out_path: str,
        language: str = "en",
        speed: float = 1.0,
    ) -> str:
        self._ensure_loaded()
        self._model.tts_to_file(
            text=text,
            speaker_wav=speaker_wav,
            language=language,
            speed=speed,
            file_path=out_path,
        )
        return out_path
