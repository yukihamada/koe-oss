"""Verify what the model actually said, using ASR on the generated audio.

This is the honest version of "reading guarantee": we transcribe our own output
and compare against the intended text. Where ASR itself is unreliable (numbers,
homophones) we mark the case *unverifiable* rather than passing or failing it.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model

MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
REF = "/Users/yukihamada/voice-clone/ref_yuki.wav"
REF_TEXT = "こんばんは、はまだゆうきです。今日は録音ボタンを押して収録しています。"
WHISPER = "mlx-community/whisper-large-v3-turbo-asr-fp16"

# (text, expected_substring_in_transcript or None)
CASES = [
    ("弟子屈は北海道にある静かな村です。", "弟子屈"),
    ("市場で買い物をしました。", None),
    ("毎月一日に支払います。", None),
    ("焚き火を囲んで話しました。", "焚き火"),
    ("これはテストです。", "テスト"),
]


def transcribe(path: str) -> str:
    from mlx_audio.stt.generate import generate_transcription

    r = generate_transcription(model=WHISPER, audio=path)
    return (getattr(r, "text", "") or "").strip()


def main() -> int:
    model = load_model(MODEL)
    from mlx_audio.stt import load as stt_load

    asr = stt_load(WHISPER)

    results = []
    for text, expect in CASES:
        chunks = [np.array(r.audio) for r in model.generate(
            text=text, ref_audio=REF, ref_text=REF_TEXT)]
        audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav = f.name
        sf.write(wav, audio, 24000)
        heard = asr.generate(wav, language="Japanese") if hasattr(asr, "generate") else None
        heard_text = (getattr(heard, "text", "") or "").strip()
        status = "unverifiable"
        if expect:
            status = "ok" if expect in heard_text else "MISMATCH"
        results.append({
            "text": text,
            "expected": expect,
            "heard": heard_text,
            "status": status,
        })
        print(json.dumps(results[-1], ensure_ascii=False))
        Path(wav).unlink(missing_ok=True)

    out = {"model": MODEL, "asr": WHISPER, "results": results}
    Path("/tmp/koeoss_readback.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2))
    print("\nwrote /tmp/koeoss_readback.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
