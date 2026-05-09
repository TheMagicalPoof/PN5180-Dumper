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
    "A5A4A3A2A1A0",
    "89ECA97F8C2A",
    "5C8FF9990DA2",
    "75CCB59C9BED",
    "D01AFEEB890A",
    "4B791BEA7BCC",
    "2612C6DE84CA",
    "707B11FC1481",
    "03F9067646AE",
    "2352C5B56D85",
    "C0C1C2C3C4C5",
    "D0D1D2D3D4D5",
    "FAFAFAFAFAFA",
    "FBFBFBFBFBFB",
    "5A1B85FCE20A",
    "E00000000000",
    "E7D6064C5860",
    "B27CCAB30DBD",
    "D2ECE8B9395E",
    "1494E81663D7",
    "7C9FB8474242",
    "569369C5A0E5",
    "632193BE1C3C",
    "644672BD4AFE",
    "8FE644038790",
    "9DE89E070277",
    "B5FF67CBA951",
    "EFF603E1EFE9",
    "F14EE7CAE863",
    "9C28A60F7249",
    "C9826AF02794",
    "FC00018778F7",
    "0297927C0F77",
    "54726176656C",
    "00000FFE2488",
    "776974687573",
    "EE0042F88840",
    "26940B21FF5D",
    "A64598A77478",
    "5C598C9C58B5",
    "E4D2770A89BE",
    "722BFCC5375F",
    "F1D83F964314",
    "505249564141",
    "505249564142",
    "47524F555041",
    "434F4D4D4F41",
    "47524F555042",
    "434F4D4D4F42",
    "4B0B20107CCB",
    "605F5E5D5C5B",
    "199404281970",
    "199404281998",
    "FFF011223358",
    "FF9F11223358",
    "AC37E76385F5",
    "576DCFFF2F25",
    "1EE38419EF39",
    "26578719DCD9",
    "000000000001",
    "000000000002",
    "00000000000A",
    "00000000000B",
    "010203040506",
    "0123456789AB",
    "100000000000",
    "111111111111",
    "123456789ABC",
    "12F2EE3478C1",
    "14D446E33363",
    "1999A3554A55",
    "200000000000",
    "222222222222",
    "27DD91F1FCF1",
    "505209016A1F",
    "2BA9621E0A36",
    "4AF9D7ADEBE4",
    "333333333333",
    "33F974B42769",
    "34D1DF9934C5",
    "43AB19EF5C31",
    "444444444444",
    "505249565441",
    "505249565442",
    "555555555555",
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
