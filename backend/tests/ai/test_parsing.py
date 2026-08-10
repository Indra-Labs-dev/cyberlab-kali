from app.ai.parsing import extract_json


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_markdown_fence():
    raw = '```json\n{"a": 1, "b": [1, 2]}\n```'
    assert extract_json(raw) == {"a": 1, "b": [1, 2]}


def test_extract_json_with_leading_prose():
    raw = 'Sure, here is the analysis:\n{"risk": "LOW"}\nLet me know if you need more.'
    assert extract_json(raw) == {"risk": "LOW"}


def test_extract_json_returns_none_for_garbage():
    assert extract_json("not json at all") is None


def test_extract_json_empty_string():
    assert extract_json("") is None
