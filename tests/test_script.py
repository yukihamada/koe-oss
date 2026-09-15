import pytest

from koe_oss.core.script import split_script, join_chunks, Chunk


def test_empty_input():
    assert split_script("") == []
    assert split_script("   ") == []


def test_single_short_sentence():
    chunks = split_script("こんにちは。")
    assert [c.text for c in chunks] == ["こんにちは。"]


def test_splits_on_sentence_enders():
    chunks = split_script("一です。二です！三ですか？")
    assert [c.text for c in chunks] == ["一です。", "二です！", "三ですか？"]


def test_respects_max_chars_by_soft_break():
    long = "あ" * 40 + "、" + "い" * 40
    chunks = split_script(long, max_chars=50)
    assert len(chunks) == 2
    assert all(c.char_len <= 50 for c in chunks)


def test_hard_cut_when_no_soft_break():
    chunks = split_script("あ" * 100, max_chars=30)
    assert len(chunks) == 4
    assert chunks[0].char_len == 30
    assert all(c.char_len <= 30 for c in chunks)


def test_index_is_sequential():
    chunks = split_script("一。二。三。")
    assert [c.index for c in chunks] == [0, 1, 2]


def test_deterministic():
    text = "弟子屈は美留和の近くです。とても静かな場所です。"
    assert [c.text for c in split_script(text)] == [c.text for c in split_script(text)]


def test_roundtrip_preserves_content():
    text = "一です。二です！三ですか？"
    chunks = split_script(text)
    joined = join_chunks(chunks)
    assert joined == text


def test_no_empty_chunks():
    text = "あ。。。。。い。"
    assert all(c.text for c in split_script(text))


def test_newline_splits():
    chunks = split_script("一行目\n二行目")
    assert len(chunks) == 2


def test_rejects_bad_max_chars():
    with pytest.raises(ValueError):
        split_script("あ", max_chars=0)


def test_chunk_is_frozen():
    c = Chunk(index=0, text="あ")
    with pytest.raises(Exception):
        c.text = "い"
