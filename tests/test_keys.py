from pn5180_dumper.keys import (
    DEFAULT_MIFARE_CLASSIC_KEYS,
    load_local_mfc_keys,
    load_proxmark_mfc_keys,
    normalize_mifare_key,
    parse_key_list,
)


def test_default_keys_are_valid_and_unique() -> None:
    parsed = parse_key_list("\n".join(DEFAULT_MIFARE_CLASSIC_KEYS))
    assert parsed == DEFAULT_MIFARE_CLASSIC_KEYS
    assert len(parsed) == len(set(parsed))
    assert len(parsed) > 4000


def test_keys_are_loaded_from_local_bundle() -> None:
    assert load_local_mfc_keys(limit=2) == DEFAULT_MIFARE_CLASSIC_KEYS[:2]
    assert load_proxmark_mfc_keys(limit=2) == DEFAULT_MIFARE_CLASSIC_KEYS[:2]


def test_parse_key_list_normalizes_and_deduplicates() -> None:
    assert parse_key_list("ff ff ff ff ff ff\nFFFFFFFFFFFF # default\na0-b0-c0-d0-e0-f0") == [
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
