"""Measure real on-device cloning: quality-adjacent timing + resource use.

This is a measurement harness, not a benchmark claim. It reports what it
observed on this machine, with this model, on this input.
"""

import json
import platform
import subprocess
import sys
import time

import mlx.core as mx
import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model

MODEL = "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16"
REF = "/Users/yukihamada/voice-clone/ref_yuki.wav"
REF_TEXT = "こんばんは、はまだゆうきです。今日は録音ボタンを押して収録しています。"
TEXTS = [
    "こんにちは。これはテストです。",
    "弟子屈は北海道にある静かな村です。",
    "今日はいい天気ですね。散歩に行きましょう。",
]


def main() -> int:
    out = {
        "model": MODEL,
        "platform": platform.platform(),
        "chip": subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
        ).stdout.strip(),
        "ref": REF,
    }

    info = sf.info(REF)
    out["ref_duration_sec"] = round(float(info.duration), 3)
    out["ref_samplerate"] = int(info.samplerate)

    t0 = time.time()
    model = load_model(MODEL)
    out["model_load_sec"] = round(time.time() - t0, 2)

    runs = []
    for i, text in enumerate(TEXTS):
        t0 = time.time()
        chunks = []
        for r in model.generate(text=text, ref_audio=REF, ref_text=REF_TEXT):
            chunks.append(np.array(r.audio))
        gen = time.time() - t0
        if not chunks:
            runs.append({"text": text, "error": "no audio produced"})
            continue
        audio = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        dur = len(audio) / 24000
        wav = f"/tmp/koeoss_out_{i}.wav"
        sf.write(wav, audio, 24000)
        runs.append(
            {
                "text": text,
                "chars": len(text),
                "gen_sec": round(gen, 2),
                "audio_sec": round(float(dur), 2),
                "realtime_factor": round(gen / dur, 2) if dur else None,
                "peak": round(float(np.abs(audio).max()), 4),
                "rms": round(float(np.sqrt((audio**2).mean())), 5),
                "wav": wav,
            }
        )
    out["runs"] = runs
    out["peak_memory_gb"] = round(mx.get_peak_memory() / 1e9, 2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
