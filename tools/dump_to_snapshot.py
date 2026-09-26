"""Regenerate pyware/offsets_snapshot.py from a fresh RbxDumperV2 offsets.cs.

Usage (from the pyWare folder):
    py tools/dump_to_snapshot.py [path/to/offsets.cs]"""
    
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "pyware" / "offsets_snapshot.py"


def parse(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    version = "unknown"
    m = re.search(r'ClientVersion\s*=\s*"([^"]+)"', text)
    if m:
        version = m.group(1)
    compiled: dict[str, int] = {}
    current = None
    for line in text.splitlines():
        mc = re.match(r"\s*public static class (\w+)", line)
        if mc:
            current = mc.group(1)
            continue
        mo = re.match(r"\s*public const long (\w+)\s*=\s*(0x[0-9a-fA-F]+|\d+)\s*;", line)
        if mo and current:
            compiled[f"{current}.{mo.group(1)}"] = int(mo.group(2), 0)
    return version, compiled


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "offsets.cs"
    version, compiled = parse(src)
    lines = [
        '"""Compiled offset snapshot generated from offsets.cs - DO NOT EDIT BY HAND.',
        "",
        "Regenerate with:  py tools/dump_to_snapshot.py [path/to/offsets.cs]",
        '"""',
        "",
        f'VERSION = "{version}"',
        "",
        "COMPILED: dict[str, int] = {",
    ]
    for k in sorted(compiled):
        lines.append(f'    "{k}": {compiled[k]},')
    lines.append("}")
    lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT}  version={version}  offsets={len(compiled)}")


if __name__ == "__main__":
    main()
