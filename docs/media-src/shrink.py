#!/usr/bin/env python3
"""shrink.py: re-save PNGs with an adaptive palette so flat-colour charts and terminal stills stay small.

Usage: python3 shrink.py COLOURS file.png [file.png ...]   (rewrites each file in place)
"""

import sys
from pathlib import Path

from PIL import Image


def main() -> int:
    colours = int(sys.argv[1])
    for name in sys.argv[2:]:
        path = Path(name)
        before = path.stat().st_size
        img = Image.open(path).convert("RGBA")
        flat = Image.new("RGB", img.size, (255, 255, 255))
        flat.paste(img, mask=img.split()[3])
        flat.quantize(colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
        print(f"{path.name}: {before // 1024} KB -> {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
