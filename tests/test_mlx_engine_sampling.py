"""The request's temperature must reach the model (it was silently dropped before)."""
import pytest

# The core test suite runs without audio libraries; this one needs them to fake a model.
np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from koe_oss.engines import mlx_qwen
from koe_oss.engines.base import SynthRequest


class _Result:
    audio = np.zeros(2400, dtype=np.float32)


class _FakeModel:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        yield _Result()


def test_synthesize_passes_the_request_temperature(tmp_path):
    ref = tmp_path / "ref.wav"
    sf.write(str(ref), np.zeros(2400, dtype=np.float32), 24000)
    engine = mlx_qwen.MlxQwenEngine()
    engine._model = _FakeModel()
    request = SynthRequest(text="こんにちは。", ref_audio=str(ref), ref_text="こんにちは。", lang="ja", out_path=str(tmp_path / "out.wav"))
    result = engine.synthesize(request)
    assert request.temperature == 0.5, "the default stays at the measured value"
    assert engine._model.calls[0]["temperature"] == 0.5
    assert result.duration_sec > 0
    request.temperature = 0.3
    engine.synthesize(request)
    assert engine._model.calls[1]["temperature"] == 0.3
