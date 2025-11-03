from __future__ import annotations


def test_extract_json() -> None:
    from cryptobot.monitor.insights import extract_json

    assert extract_json('{"a":1}') == {"a": 1}


