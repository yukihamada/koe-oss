# Licenses

## This repository

**AGPL-3.0.** See [LICENSE](../LICENSE).

AGPL permits commercial use — you may run it, sell the audio you produce, and
deploy it across a team. The obligation attaches to *modified versions offered
over a network*: if you change KOE OSS and let others use your version over a
network, you must offer them your source under the same terms.

AGPL does **not** require revenue sharing. A hosted service built around this
code is a separate commercial decision, not a license obligation.

## Upstream components

| Component | License | Notes |
|---|---|---|
| Qwen3-TTS (`Qwen/Qwen3-TTS-12Hz-*`) | Apache-2.0 | Model weights. Not redistributed here. |
| MLX-Audio (`Blaizzy/mlx-audio`) | MIT | Used by the measurement tools. |
| Apple MLX | MIT | Transitive. |
| FastAPI / Uvicorn / Pydantic | MIT | Server dependencies. |

Model weights are **not** vendored in this repository. They are downloaded at
runtime from Hugging Face under their own licenses. Check the license of any
model you install before using it commercially.

## Your recordings

This repository ships no audio. Any reference recording you register stays on
your device and is never committed.

If you contribute a sample recording to the project, it must be your own voice
(or you must hold written permission), and it must be committed under a license
that permits redistribution — stated explicitly in the PR, separate from the
code license. When in doubt, do not contribute audio.
