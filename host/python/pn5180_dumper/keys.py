DEFAULT_MIFARE_CLASSIC_KEYS = [
    "FFFFFFFFFFFF",
    "A0B0C0D0E0F0",
    "A1B1C1D1E1F1",
    "A0A1A2A3A4A5",
    "B0B1B2B3B4B5",
    "4D3A99C351DD",
    "1A982C7E459A",
    "000000000000",
    "AABBCCDDEEFF",
    "D3F7D3F7D3F7",
    "714C5C886E97",
    "587EE5F9350F",
    "A0478CC39091",
    "533CB6C723F6",
    "8FD0A4F256E9",
]


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
        candidate = line.strip()
        if not candidate:
            continue
        key = normalize_mifare_key(candidate)
        if key not in seen:
            keys.append(key)
            seen.add(key)
    return keys

