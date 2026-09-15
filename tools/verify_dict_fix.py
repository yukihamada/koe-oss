"""Does the reading dictionary actually fix the misreads we measured?

Applies koe_oss.core.readings to the text before synthesis, then transcribes
the output. Same model, same reference, same ASR — the only variable is the
dictionary. This is the evidence that "correctable readings" is real.
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model
from mlx_audio.stt import load as stt_load

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from koe_oss.core.readings import ReadingDictionary  # noqa: E402

MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
REF = "/Users/yukihamada/voice-clone/ref_yuki.wav"
REF_TEXT = "こんばんは、はまだゆうきです。今日は録音ボタンを押して収録しています。"
WHISPER = "mlx-community/whisper-large-v3-turbo-asr-fp16"

# Measured misreads (see tools/verify_readings.py output).
CASES = [
    ("弟子屈は北海道にある静かな村です。", "弟子屈", "テシカガ", "テシカガ"),
    ("焚き火を囲んで話しました。", "焚き火", "タキビ", "タキビ"),
]


def _to_kata(s: str) -> str:
    """Hiragana → katakana. Whisper writes kana-only speech in hiragana."""
    return "".join(chr(ord(c) + 96) if 0x3041 <= ord(c) <= 0x3096 else c for c in s)


def main() -> int:
    d = ReadingDictionary()
    for text, word, reading, _expect in CASES:
        d.set_reading(word, reading)

    model = load_model(MODEL)
    asr = stt_load(WHISPER)

    results = []
    for text, word, reading, expect_kana in CASES:
        applied = d.apply(text)
        chunks = [np.array(r.audio) for r in model.generate(
            text=applied, ref_audio=REF, ref_text=REF_TEXT)]
        audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        sf.write(wav, audio, 24000)
        r = asr.generate(wav, language="Japanese")
        heard = (getattr(r, "text", "") or "").strip()
        # Whisper returns hiragana for kana-only speech. Compare in katakana so
        # a script difference is not mistaken for a misread.
        heard_k = _to_kata(heard)
        results.append({
            "original": text,
            "applied": applied,
            "rule": f"{word}→{reading}",
            "heard": heard,
            "heard_katakana": heard_k,
            "expected_kana": expect_kana,
            "fixed": _to_kata(expect_kana) in heard_k,
        })
        print(json.dumps(results[-1], ensure_ascii=False))
        Path(wav).unlink(missing_ok=True)

    Path("/tmp/koeoss_dict_fix.json").write_text(
        json.dumps({"model": MODEL, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
