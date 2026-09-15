"""MLX backend for Qwen3-TTS on Apple Silicon.

This is the engine that produced the measurements in docs/STATUS.md. It is
deliberately thin: all it does is load a model and turn a SynthRequest into a
wav file. Reading correction, splitting, consent and job state live in
``koe_oss.core`` and are engine-independent.

MLX is imported lazily so the rest of the package works on machines without
Apple Silicon (and so tests never need a GPU).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from ..core.capabilities import EngineCapabilities
from .base import EngineUnavailable, SynthEngine, SynthRequest, SynthResult

DEFAULT_MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
SAMPLE_RATE = 24000

# Qwen3-TTS covers these. Declared in BOTH forms: the ISO code callers use
# ("ja") and the full name the model expects ("Japanese"). The capability gate
# matches on the declared form and returns it verbatim, so declaring only the
# full name made every "ja" request look unsupported.
_SUPPORTED = {
    "ja", "Japanese", "en", "English", "zh", "Chinese", "ko", "Korean",
    "de", "German", "fr", "French", "ru", "Russian", "pt", "Portuguese",
    "es", "Spanish", "it", "Italian",
}


class MlxQwenEngine(SynthEngine):
    """Qwen3-TTS voice cloning via MLX-Audio."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model_id = model
        self._model = None

    # ------------------------------------------------------------------ load
    def _load(self):
        if self._model is None:
            from mlx_audio.tts.utils import load_model

            self._model = load_model(self.model_id)
        return self._model

    def capabilities(self) -> EngineCapabilities:
        return EngineCapabilities(
            name=f"mlx:{self.model_id}",
            languages=set(_SUPPORTED),
            supports_clone=True,
            supports_ref_text_free=False,
            max_text_chars=1200,
        )

    def is_available(self) -> bool:
        try:
            import mlx.core  # noqa: F401
            import mlx_audio  # noqa: F401
        except ImportError:
            return False
        return True

    # -------------------------------------------------------------- synthesize
    def synthesize(self, req: SynthRequest) -> SynthResult:
        """Synthesize one chunk. Blocking; caller runs this in a subprocess."""
        import numpy as np
        import soundfile as sf

        if not Path(req.ref_audio).exists():
            raise FileNotFoundError(f"reference audio not found: {req.ref_audio}")

        model = self._load()
        t0 = time.time()
        chunks = []
        for r in model.generate(
            text=req.text,
            ref_audio=req.ref_audio,
            ref_text=req.ref_text or "",
            lang_code=_to_lang_name(req.lang),
        ):
            chunks.append(np.asarray(r.audio))
        gen = time.time() - t0

        if not chunks:
            raise EngineUnavailable("engine produced no audio")

        audio = chunks[0] if len(chunks) == 1 else np.concatenate(chunks)
        out = Path(req.out_path) if req.out_path else Path(_tmp_wav())
        out.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out), audio, SAMPLE_RATE)

        return SynthResult(
            audio_path=str(out),
            sample_rate=SAMPLE_RATE,
            duration_sec=len(audio) / SAMPLE_RATE,
            engine=self.capabilities().name,
            gen_sec=gen,
        )


def _to_lang_name(code: str) -> str:
    """'ja' -> 'Japanese'. Qwen expects the full name."""
    return {
        "ja": "Japanese", "en": "English", "zh": "Chinese", "ko": "Korean",
        "de": "German", "fr": "French", "ru": "Russian", "pt": "Portuguese",
        "es": "Spanish", "it": "Italian",
    }.get(code.lower(), "Japanese")


def _tmp_wav() -> str:
    import tempfile

    fd = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    fd.close()
    return fd.name
