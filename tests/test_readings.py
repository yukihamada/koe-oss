import pytest

from koe_oss.core.readings import ReadingDictionary, ReadingEntry, CONFIRMED, PROPOSED, REJECTED


def test_apply_replaces_confirmed_words():
    d = ReadingDictionary()
    d.set_reading("弟子屈", "テシカガ")
    assert d.apply("弟子屈に行きます") == "テシカガに行きます"


def test_proposed_is_not_applied():
    d = ReadingDictionary()
    d.propose("市場", "イチバ")
    assert d.apply("市場へ") == "市場へ"
    assert len(d.proposed_entries()) == 1


def test_confirm_promotes_proposal():
    d = ReadingDictionary()
    d.propose("市場", "イチバ")
    d.confirm("市場")
    assert d.apply("市場へ") == "イチバへ"
    assert d.get("市場").state == CONFIRMED


def test_reject_stops_reproposing():
    d = ReadingDictionary()
    d.propose("市場", "イチバ")
    d.reject("市場")
    assert d.get("市場").state == REJECTED
    assert d.apply("市場へ") == "市場へ"


def test_longest_word_wins():
    d = ReadingDictionary()
    d.set_reading("一日", "イチニチ")
    d.set_reading("毎月一日", "マイツキツイタチ")
    assert d.apply("毎月一日です") == "マイツキツイタチです"


def test_history_records_previous_value():
    d = ReadingDictionary()
    d.set_reading("KOE", "コエ")
    d.set_reading("KOE", "ケーオーイー")
    hist = d.history()
    assert len(hist) == 2
    assert hist[1]["previous"]["reading"] == "コエ"
    assert hist[1]["reading"] == "ケーオーイー"


def test_remove_is_recorded():
    d = ReadingDictionary()
    d.set_reading("焚き火", "タキビ")
    d.remove("焚き火")
    assert "焚き火" not in d
    assert d.history()[-1]["op"] == "remove"


def test_spans_report_positions():
    d = ReadingDictionary()
    d.set_reading("弟子屈", "テシカガ")
    spans = d.spans("弟子屈と弟子屈")
    assert [s["start"] for s in spans] == [0, 4]
    assert all(s["reading"] == "テシカガ" for s in spans)


def test_roundtrip_dict():
    d = ReadingDictionary()
    d.set_reading("弟子屈", "テシカガ")
    d.propose("市場", "イチバ")
    d2 = ReadingDictionary.from_dict(d.to_dict())
    assert d2.apply("弟子屈") == "テシカガ"
    assert len(d2.proposed_entries()) == 1


@pytest.mark.parametrize("bad", [{"word": "", "reading": "x"}, {"word": "a", "reading": ""}])
def test_entry_rejects_empty(bad):
    with pytest.raises(ValueError):
        ReadingEntry(**bad)


def test_entry_rejects_overlong_word():
    with pytest.raises(ValueError):
        ReadingEntry(word="あ" * 41, reading="テスト")


def test_entry_rejects_unknown_state():
    with pytest.raises(ValueError):
        ReadingEntry(word="a", reading="b", state="maybe")


def test_apply_is_pure():
    d = ReadingDictionary()
    d.set_reading("KOE", "ケーオーイー")
    text = "KOE のテスト"
    assert d.apply(text) == d.apply(text)
    assert text == "KOE のテスト"  # input untouched
