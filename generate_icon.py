#!/usr/bin/env python3
"""
Generate Unsubscribe.png (1024x1024) — the app icon — with no dependencies.

Draws a rounded blue tile, a white envelope, and a red "remove" badge, using
simple signed-distance-field coverage for smooth (anti-aliased) edges. The PNG
is written by hand via zlib (both stdlib), so this runs on a stock Mac.

  python3 generate_icon.py        # writes Unsubscribe.png next to this file
"""

import os
import zlib
import struct
import math

W = H = 1024
buf = bytearray(W * H * 4)  # RGBA, starts fully transparent


def blend(x, y, r, g, b, a):
    """Alpha-composite (r,g,b,a in 0..255/0..1) over the pixel at x,y."""
    if a <= 0 or x < 0 or y < 0 or x >= W or y >= H:
        return
    i = (y * W + x) * 4
    ba = buf[i + 3] / 255.0
    oa = a + ba * (1 - a)
    if oa <= 0:
        return
    for k, c in enumerate((r, g, b)):
        buf[i + k] = int((c * a + buf[i + k] * ba * (1 - a)) / oa)
    buf[i + 3] = int(oa * 255 + 0.5)


def rbox_sdf(px, py, cx, cy, hx, hy, rad):
    """Signed distance from (px,py) to a rounded box."""
    qx = abs(px - cx) - (hx - rad)
    qy = abs(py - cy) - (hy - rad)
    return (math.hypot(max(qx, 0), max(qy, 0))
            + min(max(qx, qy), 0) - rad)


def fill_rbox(cx, cy, hx, hy, rad, color_fn):
    """Fill a rounded box; color_fn(px,py)->(r,g,b,a) lets us do gradients."""
    x0, x1 = int(cx - hx - 2), int(cx + hx + 2)
    y0, y1 = int(cy - hy - 2), int(cy + hy + 2)
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            d = rbox_sdf(x + 0.5, y + 0.5, cx, cy, hx, hy, rad)
            cov = min(max(0.5 - d, 0.0), 1.0)  # ~1px anti-aliased edge
            if cov <= 0:
                continue
            r, g, b, a = color_fn(x, y)
            blend(x, y, r, g, b, a * cov)


def fill_circle(cx, cy, rad, color):
    r, g, b = color
    x0, x1 = int(cx - rad - 2), int(cx + rad + 2)
    y0, y1 = int(cy - rad - 2), int(cy + rad + 2)
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy) - rad
            cov = min(max(0.5 - d, 0.0), 1.0)
            if cov > 0:
                blend(x, y, r, g, b, cov)


def stroke_seg(ax, ay, bx, by, half, color):
    """Draw a rounded-cap line segment of half-width `half`."""
    r, g, b = color
    x0, x1 = int(min(ax, bx) - half - 2), int(max(ax, bx) + half + 2)
    y0, y1 = int(min(ay, by) - half - 2), int(max(ay, by) + half + 2)
    vx, vy = bx - ax, by - ay
    vlen2 = vx * vx + vy * vy or 1
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            t = ((x + 0.5 - ax) * vx + (y + 0.5 - ay) * vy) / vlen2
            t = min(max(t, 0.0), 1.0)
            d = math.hypot(x + 0.5 - (ax + t * vx),
                           y + 0.5 - (ay + t * vy)) - half
            cov = min(max(0.5 - d, 0.0), 1.0)
            if cov > 0:
                blend(x, y, r, g, b, cov)


def lerp(a, b, t):
    return tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))


def main():
    # Background tile: vertical blue gradient.
    top, bot = (0x3B, 0x82, 0xF6), (0x17, 0x43, 0xC9)
    ry0, ry1 = 96, 928

    def grad(x, y):
        t = min(max((y - ry0) / (ry1 - ry0), 0.0), 1.0)
        r, g, b = lerp(top, bot, t)
        return (r, g, b, 1.0)

    fill_rbox(512, 512, 416, 416, 200, grad)

    # Envelope body (white, slightly up).
    ecx, ecy, ehx, ehy = 512, 500, 280, 188
    fill_rbox(ecx, ecy, ehx, ehy, 36, lambda x, y: (255, 255, 255, 1.0))

    # Envelope flap: a "V" from the two top corners to the bottom-middle.
    flap = (0x64, 0x74, 0x8B)  # slate gray
    tlx, tly = ecx - ehx + 30, ecy - ehy + 34
    trx, trY = ecx + ehx - 30, ecy - ehy + 34
    midx, midy = ecx, ecy + 36
    stroke_seg(tlx, tly, midx, midy, 22, flap)
    stroke_seg(trx, trY, midx, midy, 22, flap)

    # "Remove" badge: red circle with white minus, bottom-right.
    bx, by, br = 712, 712, 150
    fill_circle(bx, by, br + 16, (255, 255, 255))  # white ring
    fill_circle(bx, by, br, (0xEF, 0x44, 0x44))    # red
    stroke_seg(bx - 78, by, bx + 78, by, 26, (255, 255, 255))  # minus

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "Unsubscribe.png")
    write_png(out)
    print("wrote", out)


def write_png(path):
    raw = bytearray()
    for y in range(H):
        raw.append(0)  # filter type 0 for each scanline
        raw += buf[y * W * 4:(y + 1) * W * 4]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(sig + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", comp) + chunk(b"IEND", b""))


if __name__ == "__main__":
    main()
