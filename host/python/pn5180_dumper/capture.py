import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import serial
from serial.tools import list_ports


HEADER_LINE = "TYPE, UID, RC, BLOCK SIZE, NUMBLOCKS, DSFID, AFI, IC REFERENCE"
COMPACT_START = "--- COMPACT HEX START ---"
COMPACT_END = "--- COMPACT HEX END ---"
NEW_DUMP_BEGIN = "DUMP_BEGIN"
NEW_DUMP_END = "DUMP_END"
NEW_META_PREFIX = "META "
NEW_COMPACT_BEGIN = "COMPACT_BEGIN"
NEW_COMPACT_END = "COMPACT_END"


@dataclass
class TagMetadata:
    tag_type: str
    uid: str
    rc: str
    block_size: int | None
    num_blocks: int | None
    dsfid: str | None
    afi: str | None
    ic_reference: str | None
    extra: dict[str, str]


class DumpCapture:
    def __init__(self) -> None:
        self.raw_lines: list[str] = []
        self.metadata: TagMetadata | None = None
        self.compact_hex_lines: list[str] = []
        self.compact_hex_display_lines: list[str] = []
        self.compact_block_statuses: list[str] = []
        self._expect_metadata = False
        self._in_compact_hex = False
        self._in_dump = False
        self._pending_block_status = "OK"

    def reset(self) -> None:
        self.__init__()

    def feed(self, line: str) -> bool:
        self.raw_lines.append(line)

        if line == NEW_DUMP_BEGIN:
            self._in_dump = True
            self.metadata = None
            self.compact_hex_lines = []
            self.compact_hex_display_lines = []
            self.compact_block_statuses = []
            self._expect_metadata = False
            self._in_compact_hex = False
            self._pending_block_status = "OK"
            return False

        if line == NEW_DUMP_END:
            done = self.is_complete()
            self._in_dump = False
            self._in_compact_hex = False
            self._expect_metadata = False
            return done

        if line.startswith(NEW_META_PREFIX):
            self.metadata = parse_new_metadata(line)
            return False

        if line == NEW_COMPACT_BEGIN:
            self._in_compact_hex = True
            self.compact_hex_lines = []
            self.compact_hex_display_lines = []
            self.compact_block_statuses = []
            self._pending_block_status = "OK"
            return False

        if line == NEW_COMPACT_END:
            self._in_compact_hex = False
            return False

        if line == HEADER_LINE:
            self._expect_metadata = True
            return False

        if self._expect_metadata:
            self.metadata = parse_metadata(line)
            self._expect_metadata = False
            return False

        if line == COMPACT_START:
            self._in_compact_hex = True
            self.compact_hex_lines = []
            self.compact_block_statuses = []
            self._pending_block_status = "OK"
            return False

        if line == COMPACT_END:
            self._in_compact_hex = False
            return self.is_complete()

        if self._in_compact_hex:
            if line.startswith("INFO mfclassic_block_key_missing "):
                self._pending_block_status = "MS"
                return False
            if line.startswith("INFO mfclassic_block_missing "):
                self._pending_block_status = "NN"
                return False
            if line.startswith("INFO mfclassic_block ") or line.startswith("INFO typea_read "):
                self._pending_block_status = "OK"
                return False

            compact = normalize_hex_line(line)
            if compact:
                self.compact_hex_lines.append(compact)
                self.compact_hex_display_lines.append(spaced_hex_line(compact))
                self.compact_block_statuses.append(self._pending_block_status)
                self._pending_block_status = "OK"
            return False

        if line.startswith("INFO ") or line.startswith("ERROR ") or line.startswith("READER_READY"):
            return False

        return False

    def is_complete(self) -> bool:
        if self.metadata is None:
            return False
        return bool(self.compact_hex_lines) or self.metadata.uid not in {"", "-"}


def normalize_hex_line(line: str) -> str | None:
    compact = line.strip().replace(" ", "")
    if not compact:
        return None
    if not re.fullmatch(r"[0-9A-Fa-f]+", compact):
        return None
    return compact.upper()


def spaced_hex_line(compact: str) -> str:
    return " ".join(compact[i:i + 2] for i in range(0, len(compact), 2))


def parse_metadata(line: str) -> TagMetadata:
    parts = [part.strip() for part in line.split(",")]
    if len(parts) != 8:
        raise ValueError(f"Unexpected metadata line: {line!r}")

    return TagMetadata(
        tag_type=parts[0],
        uid=parts[1],
        rc=parts[2],
        block_size=parse_optional_int(parts[3]),
        num_blocks=parse_optional_int(parts[4]),
        dsfid=parse_optional_text(parts[5]),
        afi=parse_optional_text(parts[6]),
        ic_reference=parse_optional_text(parts[7]),
        extra={},
    )


def parse_new_metadata(line: str) -> TagMetadata:
    payload = line[len(NEW_META_PREFIX):].strip()
    fields: dict[str, str] = {}
    for part in payload.split():
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        fields[key] = value

    known_fields = {
        "type",
        "uid",
        "rc",
        "block_size",
        "num_blocks",
        "dsfid",
        "afi",
        "ic_reference",
    }

    return TagMetadata(
        tag_type=fields.get("type", "-"),
        uid=fields.get("uid", "-"),
        rc=fields.get("rc", "-"),
        block_size=parse_optional_int(fields.get("block_size", "-")),
        num_blocks=parse_optional_int(fields.get("num_blocks", "-")),
        dsfid=parse_optional_text(fields.get("dsfid", "-")),
        afi=parse_optional_text(fields.get("afi", "-")),
        ic_reference=parse_optional_text(fields.get("ic_reference", "-")),
        extra={
            key: value
            for key, value in fields.items()
            if key not in known_fields and value not in {"", "-"}
        },
    )


def parse_optional_int(value: str) -> int | None:
    if value in {"-", ""}:
        return None
    return int(value)


def parse_optional_text(value: str) -> str | None:
    if value in {"-", ""}:
        return None
    return value


def detect_port(preferred: str | None) -> str:
    if preferred:
        return preferred

    ports = [port.device for port in list_ports.comports()]
    filtered = [port for port in ports if port.upper() != "COM1"]

    if len(filtered) == 1:
        return filtered[0]

    if not filtered and ports:
        raise RuntimeError(
            "Only COM1 was found. This is usually not the board. "
            "Connect the device or pass --port COMx explicitly."
        )

    if not ports:
        raise RuntimeError("No serial ports found.")

    raise RuntimeError(
        "Could not auto-select serial port. Available ports: "
        + ", ".join(filtered or ports)
        + ". Pass --port COMx explicitly."
    )


def dump_to_bytes(lines: list[str]) -> bytes:
    data = bytearray()
    for line in lines:
        data.extend(bytes.fromhex(line))
    return bytes(data)


def sanitize_uid(uid: str) -> str:
    return uid.replace(":", "-").replace("/", "-")


def save_capture(capture: DumpCapture, out_dir: Path) -> Path:
    assert capture.metadata is not None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = sanitize_uid(capture.metadata.uid or "unknown")
    target_dir = out_dir / f"{timestamp}_{uid}"
    target_dir.mkdir(parents=True, exist_ok=True)

    binary = dump_to_bytes(capture.compact_hex_lines)
    has_dump = bool(capture.compact_hex_lines)
    sha256 = hashlib.sha256(binary).hexdigest() if has_dump else None

    metadata = {
        "captured_at_utc": timestamp,
        "type": capture.metadata.tag_type,
        "uid": capture.metadata.uid,
        "rc": capture.metadata.rc,
        "block_size": capture.metadata.block_size,
        "num_blocks": capture.metadata.num_blocks,
        "dsfid": capture.metadata.dsfid,
        "afi": capture.metadata.afi,
        "ic_reference": capture.metadata.ic_reference,
        "sha256": sha256,
        "byte_length": len(binary),
        "has_dump": has_dump,
    }
    metadata.update(capture.metadata.extra)

    (target_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if capture.compact_hex_lines:
        (target_dir / "dump.hex").write_text(
            "\n".join(capture.compact_hex_display_lines) + "\n",
            encoding="ascii",
        )
        (target_dir / "block_status.json").write_text(
            json.dumps(capture.compact_block_statuses, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    (target_dir / "raw_serial.log").write_text(
        "\n".join(capture.raw_lines) + "\n",
        encoding="utf-8",
    )
    if capture.compact_hex_lines:
        (target_dir / "dump.bin").write_bytes(binary)

    return target_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capture PN5180 Dumper streaming records from the serial output."
    )
    parser.add_argument("--port", help="Serial port, e.g. COM6")
    parser.add_argument(
        "--auto-port",
        action="store_true",
        help="Auto-detect the serial port",
    )
    parser.add_argument("--baud", type=int, default=460800, help="Baud rate")
    parser.add_argument(
        "--out-dir",
        default="captures",
        help="Directory where captured dumps will be stored",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Exit after saving the first complete dump",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        preferred_port = args.port
        if args.auto_port:
            preferred_port = None
        port_name = detect_port(preferred_port)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Opening {port_name} @ {args.baud}...")

    capture = DumpCapture()

    try:
        with serial.Serial(
            port=port_name,
            baudrate=args.baud,
            timeout=0.5,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            dsrdtr=False,
            rtscts=False,
        ) as ser:
            ser.dtr = False
            ser.rts = False
            time.sleep(1.0)

            while True:
                raw = ser.readline()
                if not raw:
                    continue

                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                print(line)

                try:
                    complete = capture.feed(line)
                except Exception as exc:
                    print(f"WARNING: parse error: {exc}", file=sys.stderr)
                    capture.reset()
                    continue

                if complete:
                    target_dir = save_capture(capture, out_dir)
                    print(f"Saved dump to {target_dir}")
                    if args.once:
                        return 0
                    capture.reset()

    except serial.SerialException as exc:
        print(f"ERROR: serial failure: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
