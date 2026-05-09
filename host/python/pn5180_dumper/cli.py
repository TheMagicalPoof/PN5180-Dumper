import argparse
import json
import sys
from dataclasses import asdict, dataclass

from serial.tools import list_ports

from . import __version__
from .capture import main as capture_main


@dataclass
class SerialPortInfo:
    device: str
    description: str
    hwid: str
    manufacturer: str | None
    product: str | None
    serial_number: str | None


def iter_ports() -> list[SerialPortInfo]:
    return [
        SerialPortInfo(
            device=port.device,
            description=port.description,
            hwid=port.hwid,
            manufacturer=port.manufacturer,
            product=port.product,
            serial_number=port.serial_number,
        )
        for port in list_ports.comports()
    ]


def command_ports(args: argparse.Namespace) -> int:
    ports = iter_ports()
    if args.json:
        print(json.dumps([asdict(port) for port in ports], ensure_ascii=False, indent=2))
        return 0

    if not ports:
        print("No serial ports found.")
        return 1

    for port in ports:
        print(f"{port.device:>8}  {port.description}  {port.hwid}")
    return 0


def command_capture(args: argparse.Namespace) -> int:
    capture_args: list[str] = []
    if args.port:
        capture_args.extend(["--port", args.port])
    if args.auto_port:
        capture_args.append("--auto-port")
    if args.baud:
        capture_args.extend(["--baud", str(args.baud)])
    if args.out_dir:
        capture_args.extend(["--out-dir", args.out_dir])
    if args.once:
        capture_args.append("--once")
    return capture_main(capture_args)


def command_not_implemented(args: argparse.Namespace) -> int:
    print(
        f"The '{args.command}' command is reserved for the upcoming firmware "
        "command protocol. Use 'capture' with the current streaming firmware."
    )
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pn5180-dumper",
        description="Host CLI for PN5180 Dumper.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    ports = subparsers.add_parser("ports", help="List available serial ports")
    ports.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    ports.set_defaults(func=command_ports)

    capture = subparsers.add_parser("capture", help="Capture records from current streaming firmware")
    capture.add_argument("--port", help="Serial port, e.g. COM6 or /dev/ttyUSB0")
    capture.add_argument("--auto-port", action="store_true", help="Auto-detect the serial port")
    capture.add_argument("--baud", type=int, default=460800, help="Baud rate")
    capture.add_argument("--out-dir", default="captures", help="Directory for captured records")
    capture.add_argument("--once", action="store_true", help="Exit after first complete record")
    capture.set_defaults(func=command_capture)

    for name in ("scan", "identify", "read", "write", "dump", "config"):
        command = subparsers.add_parser(name, help=f"Reserved future command: {name}")
        command.set_defaults(func=command_not_implemented)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

