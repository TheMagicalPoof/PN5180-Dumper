from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "host" / "python"))

from pn5180_dumper.capture import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
