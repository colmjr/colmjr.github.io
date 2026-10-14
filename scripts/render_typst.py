#!/usr/bin/env python3
"""Precompile {{< typst >}} shortcode blocks in content/ to SVG.

Hugo templates can't run external programs, so this script runs before
`hugo` and does the compilation with the typst CLI. The shortcode in
layouts/shortcodes/typst.html hashes the (trimmed) shortcode body with
SHA-1 and inlines assets/typst-gen/<hash>.svg, so this script must
produce exactly those hashes.

Run:  python3 scripts/render_typst.py
Requires: typst on PATH.
"""

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
OUT_DIR = ROOT / "assets" / "typst-gen"

# {{< typst >}}...{{< /typst >}} or {{< typst inline=true >}}...
# Params are part of the opening tag only and do not affect the hash.
BLOCK_RE = re.compile(
    r"\{\{<\s*typst\b[^>]*>\}\}(.*?)\{\{<\s*/typst\s*>\}\}",
    re.DOTALL,
)

# fill: none -> transparent background; auto width/height -> snug fit
WRAPPER = """#set page(width: auto, height: auto, margin: 2pt, fill: none)
#set text(size: 12pt)
{src}
"""


def hash_src(src: str) -> str:
    # Must match `sha1 (trim .Inner " \t\r\n")` in the shortcode.
    return hashlib.sha1(src.strip(" \t\r\n").encode("utf-8")).hexdigest()


def render(src: str, dest: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        typ_file = Path(tmp) / "snippet.typ"
        typ_file.write_text(WRAPPER.format(src=src.strip(" \t\r\n")), encoding="utf-8")
        proc = subprocess.run(
            ["typst", "compile", "--format", "svg", str(typ_file), str(dest)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"error: typst failed for snippet:\n{src}\n{proc.stderr}", file=sys.stderr)
            sys.exit(1)
    # Inherit the surrounding text color so dark mode works.
    svg = dest.read_text(encoding="utf-8")
    for attr in ("fill", "stroke"):
        svg = svg.replace(f'{attr}="#000000"', f'{attr}="currentColor"')
    dest.write_text(svg, encoding="utf-8")


def main() -> None:
    if shutil.which("typst") is None:
        print("error: typst not found on PATH", file=sys.stderr)
        sys.exit(1)

    wanted = {}
    for path in sorted(CONTENT.rglob("*")):
        if path.suffix not in (".org", ".md"):
            continue
        for match in BLOCK_RE.finditer(path.read_text(encoding="utf-8")):
            src = match.group(1)
            wanted[hash_src(src)] = src

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    stale = [p for p in OUT_DIR.glob("*.svg") if p.stem not in wanted]
    for p in stale:
        print(f"pruned stale {p.relative_to(ROOT)}")
        p.unlink()

    compiled = 0
    for h, src in wanted.items():
        dest = OUT_DIR / f"{h}.svg"
        if dest.exists():
            continue
        render(src, dest)
        compiled += 1

    print(f"typst: {len(wanted)} block(s), {compiled} compiled, {len(stale)} pruned")


if __name__ == "__main__":
    main()
