import json
from importlib import resources


LOCAL_MIFARE_CLASSIC_KEYS_RESOURCE = "data/mifare_classic_keys.json"


def normalize_mifare_key(value: str) -> str:
    compact = "".join(ch for ch in value if ch in "0123456789abcdefABCDEF").upper()
    if len(compact) != 12:
        raise ValueError(f"MIFARE Classic key must be 6 bytes / 12 hex chars: {value!r}")
    bytes.fromhex(compact)
    return compact


def parse_key_list(text: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for line in text.replace(",", "\n").replace(";", "\n").splitlines():
        candidate = line.split("#", 1)[0].strip()
        if not candidate:
            continue
        key = normalize_mifare_key(candidate)
        if key not in seen:
            keys.append(key)
            seen.add(key)
    return keys


def load_local_mfc_keys(limit: int | None = None) -> list[str]:
    resource = resources.files("pn5180_dumper").joinpath(LOCAL_MIFARE_CLASSIC_KEYS_RESOURCE)
    payload = json.loads(resource.read_text(encoding="utf-8"))
    keys = parse_key_list("\n".join(payload["keys"]))
    if limit is not None:
        return keys[:limit]
    return keys


def load_proxmark_mfc_keys(limit: int | None = None) -> list[str]:
    """Compatibility wrapper: loads the bundled local key dictionary only."""
    return load_local_mfc_keys(limit=limit)


DEFAULT_MIFARE_CLASSIC_KEYS = load_local_mfc_keys()
