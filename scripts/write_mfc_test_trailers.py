import argparse
import json
import re
import sys
import time
from pathlib import Path

import serial


DEFAULT_BAUD = 460800
TRANSPORT_ACCESS_BITS = "FF078069"
DEFAULT_KEY = "FFFFFFFFFFFF"
TEST_SECTORS_1K = [1, 8, 15]


def load_keys() -> list[str]:
    path = Path(__file__).resolve().parents[1] / "host/python/pn5180_dumper/data/mifare_classic_keys.json"
    return json.loads(path.read_text(encoding="utf-8"))["keys"]


def trailer_block_for_sector(sector: int) -> int:
    if sector < 32:
        return sector * 4 + 3
    return 128 + (sector - 32) * 16 + 15


def parse_fields(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in line.split():
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key] = value
    return fields


def read_until(ser: serial.Serial, patterns: tuple[str, ...], timeout: float = 5.0) -> list[str]:
    end = time.time() + timeout
    lines: list[str] = []
    while time.time() < end:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        print(line)
        lines.append(line)
        if any(line.startswith(pattern) for pattern in patterns):
            return lines
    return lines


def command(ser: serial.Serial, text: str, wait_for: tuple[str, ...], timeout: float = 5.0) -> list[str]:
    print(f"> {text}")
    ser.write((text + "\n").encode("ascii"))
    ser.flush()
    return read_until(ser, wait_for, timeout=timeout)


def selected_test_keys(keys: list[str]) -> list[str]:
    return [keys[1], keys[len(keys) // 2], keys[-1]]


def build_trailer(key: str) -> str:
    return f"{key}{TRANSPORT_ACCESS_BITS}{key}"


def write_trailer(ser: serial.Serial, block: int, data: str, auth_key: str) -> bool:
    lines = command(
        ser,
        f"PND1 WRITE {block} {data} ALLOWTRAILER KEY={auth_key}",
        ("PND1 WRITE_RESULT",),
        timeout=8.0,
    )
    return any(re.search(r"status=ok\b", line) for line in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a disposable MIFARE Classic test tag with custom sector keys.")
    parser.add_argument("--port", default="COM6")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD)
    parser.add_argument("--restore", action="store_true", help="Restore the same test sectors back to FFFFFFFFFFFF.")
    args = parser.parse_args()

    keys = load_keys()
    test_keys = selected_test_keys(keys)

    with serial.Serial(args.port, args.baud, timeout=0.5, dsrdtr=False, rtscts=False) as ser:
        ser.dtr = False
        ser.rts = False
        time.sleep(1.0)
        ser.reset_input_buffer()

        lines = command(ser, "PND1 SCAN", ("TAG_DETECTED", "INFO no_card"), timeout=5.0)
        tag_line = next((line for line in lines if line.startswith("TAG_DETECTED")), "")
        fields = parse_fields(tag_line)
        family = fields.get("family", "")
        if not family.startswith("MIFARE_CLASSIC"):
            print(f"ERROR: current tag is not MIFARE Classic: {family or 'none'}", file=sys.stderr)
            return 2

        for sector, key in zip(TEST_SECTORS_1K, test_keys):
            block = trailer_block_for_sector(sector)
            if args.restore:
                data = build_trailer(DEFAULT_KEY)
                auth_key = key
                label = f"restore sector {sector} trailer block {block}"
            else:
                data = build_trailer(key)
                auth_key = DEFAULT_KEY
                label = f"lock sector {sector} trailer block {block} with key {key}"

            print(f"INFO {label}")
            if write_trailer(ser, block, data, auth_key):
                continue
            if not args.restore and write_trailer(ser, block, data, key):
                print(f"INFO sector {sector} already accepted target key; continuing")
                continue
            print(f"ERROR: failed to write sector {sector} trailer block {block}", file=sys.stderr)
            return 3

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
