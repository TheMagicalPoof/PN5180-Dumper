$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist\python-qt"
$buildRoot = Join-Path $root "build\python-qt"
$pyinstallerWork = Join-Path $root "build\pyinstaller"
$entry = Join-Path $buildRoot "pndumper_qt_entry.py"
$icon = Join-Path $buildRoot "d20.ico"
$logoSource = Join-Path $root "scripts\d20.png"
$keysSource = Join-Path $root "host\python\pn5180_dumper\data\mifare_classic_keys.json"
$keysTarget = Join-Path $dist "mifare_keys.json"
$readme = Join-Path $dist "README_RUN.txt"

New-Item -ItemType Directory -Force $dist, $buildRoot, $pyinstallerWork | Out-Null

@"
from pn5180_dumper.qt_app import main

raise SystemExit(main())
"@ | Set-Content -LiteralPath $entry -Encoding UTF8

@"
from pathlib import Path
from PIL import Image

root = Path(r"$root")
source = root / "scripts" / "d20.png"
target = Path(r"$icon")
image = Image.open(source).convert("RGBA")
image.save(target, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
"@ | python -

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name PNDumper `
    --icon $icon `
    --paths (Join-Path $root "host\python") `
    --distpath $dist `
    --workpath $pyinstallerWork `
    --specpath $pyinstallerWork `
    --add-data "$keysSource;pn5180_dumper\data" `
    --add-data "$logoSource;assets" `
    $entry

Copy-Item -LiteralPath $keysSource -Destination $keysTarget -Force

@"
PNDumper Python/Qt release

Run:
  PNDumper.exe

Required files:
  PNDumper.exe
  mifare_keys.json

Notes:
  - This is the stable Python/Qt application packaged as a Windows exe.
  - Keep mifare_keys.json next to PNDumper.exe so the key dictionary can be updated without rebuilding.
  - Captures are saved to the captures folder relative to where you run the exe.
"@ | Set-Content -LiteralPath $readme -Encoding UTF8

Write-Host "Built $(Join-Path $dist 'PNDumper.exe')"
