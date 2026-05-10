import json
import re

from pn5180_dumper.capture import DumpCapture, save_capture


def feed_capture(lines: list[str]) -> DumpCapture:
    capture = DumpCapture()
    for line in lines:
        capture.feed(line)
    return capture


def test_mifare_compact_block_statuses_are_parsed() -> None:
    capture = feed_capture(
        [
            "DUMP_BEGIN",
            (
                "META type=ISO14443A protocol=ISO14443A uid=C363AE0E uid_length=4 "
                "rc=0 block_size=16 num_blocks=3 family=MIFARE_CLASSIC_1K"
            ),
            "COMPACT_BEGIN",
            "INFO mfclassic_block block=0",
            "C3 63 AE 0E 00 08 04 00 62 63 64 65 66 67 68 69",
            "INFO mfclassic_block_missing block=1",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            "INFO mfclassic_block_key_missing block=2",
            "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00",
            "COMPACT_END",
            "DUMP_END",
        ]
    )

    assert capture.is_complete()
    assert capture.compact_block_statuses == ["OK", "NN", "MS"]
    assert len(capture.compact_hex_lines) == 3


def test_save_capture_uses_timestamp_and_hash_folder(tmp_path) -> None:
    capture = feed_capture(
        [
            "DUMP_BEGIN",
            "META type=ISO14443A protocol=ISO14443A uid=C363AE0E uid_length=4 rc=0 block_size=16 num_blocks=1",
            "COMPACT_BEGIN",
            "INFO mfclassic_block block=0",
            "C3 63 AE 0E 00 08 04 00 62 63 64 65 66 67 68 69",
            "COMPACT_END",
            "DUMP_END",
        ]
    )

    folder = save_capture(capture, tmp_path / "captures")

    assert re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", folder.name)
    assert (folder / "dump.bin").read_bytes() == bytes.fromhex("C363AE0E000804006263646566676869")
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["uid"] == "C363AE0E"
    assert metadata["byte_length"] == 16
    assert metadata["sha256"].startswith(folder.name.split("_", 1)[1])
