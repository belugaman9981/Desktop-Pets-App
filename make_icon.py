#!/usr/bin/env python3
"""
Generate pets.ico - a little bird icon for the Desktop Pets shortcuts.

Run with:  py -3 make_icon.py
"""

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIZES = (16, 32, 48, 64, 128, 256)

BODY = (226, 59, 59)
BELLY = (246, 184, 184)
BEAK = (255, 159, 26)
EYE = (20, 20, 20)
WHITE = (255, 255, 255)


def blend(base, top, alpha):
    return tuple(round(b + (t - b) * alpha) for b, t in zip(base, top))


def render(size):
    """Return BGRA pixel rows for one icon size, drawn with simple shapes."""
    cx, cy = size / 2, size / 2
    r = size * 0.34
    rows = []
    for y in range(size):
        row = []
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            color = None

            # body ellipse
            dx, dy = (px - cx) / r, (py - cy) / (r * 0.92)
            if dx * dx + dy * dy <= 1.0:
                color = BODY
                # belly ellipse
                bx, by = (px - cx * 1.05) / (r * 0.62), (py - cy * 1.25) / (r * 0.55)
                if bx * bx + by * by <= 1.0:
                    color = BELLY

            # beak triangle on the right
            if color is not None and px > cx + r * 0.72:
                span = (px - (cx + r * 0.72)) / (r * 0.42)
                if span <= 1.0 and abs(py - cy) <= r * 0.22 * (1.0 - span):
                    color = BEAK

            # eye
            ex, ey = (px - cx * 1.28) / (r * 0.24), (py - cy * 0.72) / (r * 0.24)
            if ex * ex + ey * ey <= 1.0:
                color = WHITE
                ix, iy = (px - cx * 1.32) / (r * 0.12), (py - cy * 0.72) / (r * 0.12)
                if ix * ix + iy * iy <= 1.0:
                    color = EYE

            # wing
            wx, wy = (px - cx * 0.62) / (r * 0.42), (py - cy * 0.72) / (r * 0.62)
            if color is not None and wx * wx + wy * wy <= 1.0:
                color = blend(BELLY, BODY, 0.35)

            if color is None:
                row.append((0, 0, 0, 0))
            else:
                row.append((color[2], color[1], color[0], 255))
        rows.append(row)
    return rows


def bmp_bytes(rows, size):
    """32-bit BGRA DIB payload: header + bottom-up pixels + AND mask."""
    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
    pixels = b"".join(
        bytes(channel for pixel in row for channel in pixel)
        for row in reversed(rows)
    )
    mask_stride = ((size + 31) // 32) * 4
    mask = b"\x00" * (mask_stride * size)
    return header + pixels + mask


def main():
    images = [(size, bmp_bytes(render(size), size)) for size in SIZES]
    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, data in images:
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    for _, data in images:
        out += data

    target = HERE / "pets.ico"
    target.write_bytes(bytes(out))
    print(f"Wrote {target} ({len(out)} bytes, {len(images)} sizes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
