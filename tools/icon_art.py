"""Deterministic Apps-screen icon for the stock TrimUI launcher.

Matches the stock icon template: a 300x300 transparent canvas holding a
centered 200x200 continuous-corner tile. The mark is the PocketLAB library
symbol, an orange disc with a paper plus, drawn with analytic anti-aliasing.
"""
from pathlib import Path
import math
import struct
import zlib

SIZE = 300
TILE = (50.0, 50.0, 250.0, 250.0)
CORNER, EXPONENT = 56.0, 2.75  # Fitted to the stock User Guide/RetroArch tile mask.
PAPER = (241, 240, 233)


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def coverage(distance):
    return min(1.0, max(0.0, 0.5 - distance))


def tile_distance(x, y):
    left, top, right, bottom = TILE
    cx = min(max(x, left + CORNER), right - CORNER)
    cy = min(max(y, top + CORNER), bottom - CORNER)
    dx, dy = abs(x - cx), abs(y - cy)
    if dx == 0 or dy == 0:
        return max(left - x, x - right, top - y, y - bottom)
    return (dx ** EXPONENT + dy ** EXPONENT) ** (1 / EXPONENT) - CORNER


def capsule_distance(x, y, ax, ay, bx, by, radius):
    vx, vy = bx - ax, by - ay
    t = min(1.0, max(0.0, ((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy)))
    return math.hypot(x - ax - vx * t, y - ay - vy * t) - radius


def pixel(x, y):
    px, py = x + 0.5, y + 0.5
    alpha = coverage(tile_distance(px, py))
    if not alpha:
        return (0, 0, 0, 0)
    # Warm paper face with a soft top light, like the stock tiles' gradient.
    t = (py - TILE[1]) / (TILE[3] - TILE[1])
    color = mix((248, 247, 241), (214, 212, 200), t ** 1.2)
    color = mix(color, (255, 255, 252), max(0.0, 1 - math.hypot(px - 150, py - 30) / 150) * 0.35)
    # A light inner rim crisps the silhouette on dark launcher themes.
    rim = coverage(-tile_distance(px, py) - 3.0)
    color = mix(mix(color, (255, 255, 255), 0.5), color, rim)
    # Orange control disc with a subtle top-left light and a low shadow.
    shadow = coverage(math.hypot(px - 150, py - 155) - 66) * 0.12
    color = mix(color, (8, 12, 14), shadow)
    disc = coverage(math.hypot(px - 150, py - 150) - 64)
    if disc:
        light = max(0.0, min(1.0, ((150 - px) + (150 - py)) / 180 + 0.5))
        face = mix((222, 66, 24), (252, 112, 66), light)
        color = mix(color, face, disc)
        plus = max(coverage(capsule_distance(px, py, 118, 150, 182, 150, 4.5)),
                   coverage(capsule_distance(px, py, 150, 118, 150, 182, 4.5)))
        color = mix(color, PAPER, plus * disc)
    return (*(round(c) for c in color), round(alpha * 255))


def render():
    pixels = bytearray()
    for y in range(SIZE):
        pixels.append(0)
        for x in range(SIZE):
            pixels.extend(pixel(x, y))
    return bytes(pixels)


def write_icon(path):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    header = struct.pack('>IIBBBBB', SIZE, SIZE, 8, 6, 0, 0, 0)
    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) +
           chunk(b'IDAT', zlib.compress(render(), 9)) + chunk(b'IEND', b''))
    Path(path).write_bytes(png)
