from pn5180_dumper.keys import DEFAULT_MIFARE_CLASSIC_KEYS, normalize_mifare_key, parse_key_list


def test_default_keys_are_valid_and_unique() -> None:
    parsed = parse_key_list("\n".join(DEFAULT_MIFARE_CLASSIC_KEYS))
    assert parsed == DEFAULT_MIFARE_CLASSIC_KEYS
    assert len(parsed) == len(set(parsed))
    assert len(parsed) == 100


def test_parse_key_list_normalizes_and_deduplicates() -> None:
    assert parse_key_list("ff ff ff ff ff ff\nFFFFFFFFFFFF\na0-b0-c0-d0-e0-f0") == [
        "FFFFFFFFFFFF",
        "A0B0C0D0E0F0",
    ]


def test_normalize_rejects_wrong_length() -> None:
    try:
        normalize_mifare_key("FFFF")
    except ValueError as exc:
        assert "12 hex chars" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
