import json
import sys
from importlib import resources
from pathlib import Path


LOCAL_MIFARE_CLASSIC_KEYS_RESOURCE = "data/mifare_classic_keys.json"
EXTERNAL_MIFARE_CLASSIC_KEYS_FILE = "mifare_keys.json"


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


def _external_key_paths() -> list[Path]:
    paths: list[Path] = []
    if getattr(sys, "frozen", False):
        paths.append(Path(sys.executable).resolve().parent / EXTERNAL_MIFARE_CLASSIC_KEYS_FILE)
    paths.append(Path.cwd() / EXTERNAL_MIFARE_CLASSIC_KEYS_FILE)
    return paths


def _keys_from_json_text(text: str) -> list[str]:
    payload = json.loads(text)
    if isinstance(payload, dict):
        values = payload.get("keys", [])
    else:
        values = payload
    if not isinstance(values, list):
        raise ValueError("mifare_keys.json must contain a JSON list or an object with a 'keys' list")
    return parse_key_list("\n".join(str(value) for value in values))


def load_local_mfc_keys(limit: int | None = None) -> list[str]:
    for path in _external_key_paths():
        if path.is_file():
            keys = _keys_from_json_text(path.read_text(encoding="utf-8"))
            return keys[:limit] if limit is not None else keys

    resource = resources.files("pn5180_dumper").joinpath(LOCAL_MIFARE_CLASSIC_KEYS_RESOURCE)
    keys = _keys_from_json_text(resource.read_text(encoding="utf-8"))
    if limit is not None:
        return keys[:limit]
    return keys


def load_proxmark_mfc_keys(limit: int | None = None) -> list[str]:
    """Compatibility wrapper: loads the bundled local key dictionary only."""
    return load_local_mfc_keys(limit=limit)


DEFAULT_MIFARE_CLASSIC_KEYS = load_local_mfc_keys()
