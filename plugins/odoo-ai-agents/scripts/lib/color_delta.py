#!/usr/bin/env python3
"""color_delta.py - perceptual color distance (CIEDE2000) for brand-fidelity checks.

Brand-agnostic helper used by verify-frontend's optional brand block:
given an EXPECTED brand token value (declared by the consumer) and the ACTUAL value
rendered by the running instance (read via getComputedStyle), compute the perceptual
deltaE so SCSS shorthand / rgb() / hex variations don't trip a naive string compare.

Stdlib only (math). No third-party deps; no brand values are embedded here.

CLI:
    color_delta.py "<expected>" "<actual>"      -> prints deltaE2000 (float), exit 0
    color_delta.py --threshold T "<e>" "<a>"    -> exit 0 if deltaE<=T else exit 1
Accepts: #rgb, #rrggbb, rgb(r,g,b), rgba(r,g,b,a), or "r,g,b".
Exit 2 on unparseable input (caller treats as soft-skip).
"""
import math
import re
import sys


def parse_color(s):
    """Return (r, g, b) in 0-255, or None if unparseable."""
    if s is None:
        return None
    s = s.strip().strip('"').strip("'").lower()
    if not s:
        return None
    m = re.fullmatch(r"#([0-9a-f]{3})", s)
    if m:
        return tuple(int(c * 2, 16) for c in m.group(1))
    m = re.fullmatch(r"#([0-9a-f]{6})", s)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"(?:rgba?\()?\s*([0-9.]+)\s*[, ]\s*([0-9.]+)\s*[, ]\s*([0-9.]+)"
                     r"(?:\s*[,/]\s*[0-9.%]+)?\s*\)?", s)
    if m:
        try:
            return tuple(min(255, max(0, round(float(m.group(i))))) for i in (1, 2, 3))
        except ValueError:
            return None
    return None


def _srgb_to_lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb):
    r, g, b = (_srgb_to_lin(v) for v in rgb)
    # sRGB D65 -> XYZ
    x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047
    y = (r * 0.2126729 + g * 0.7151522 + b * 0.0721750)
    z = (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def ciede2000(lab1, lab2):
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    avg_Lp = (L1 + L2) / 2.0
    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    avg_C = (C1 + C2) / 2.0
    G = 0.5 * (1 - math.sqrt(avg_C ** 7 / (avg_C ** 7 + 25 ** 7))) if avg_C else 0.0
    a1p, a2p = a1 * (1 + G), a2 * (1 + G)
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    avg_Cp = (C1p + C2p) / 2.0

    def hp(ap, b):
        if ap == 0 and b == 0:
            return 0.0
        h = math.degrees(math.atan2(b, ap))
        return h + 360 if h < 0 else h

    h1p, h2p = hp(a1p, b1), hp(a2p, b2)
    dLp = L2 - L1
    dCp = C2p - C1p
    if C1p * C2p == 0:
        dhp = 0.0
    elif abs(h2p - h1p) <= 180:
        dhp = h2p - h1p
    elif h2p - h1p > 180:
        dhp = h2p - h1p - 360
    else:
        dhp = h2p - h1p + 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2.0)

    if C1p * C2p == 0:
        avg_hp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        avg_hp = (h1p + h2p) / 2.0
    elif h1p + h2p < 360:
        avg_hp = (h1p + h2p + 360) / 2.0
    else:
        avg_hp = (h1p + h2p - 360) / 2.0

    T = (1 - 0.17 * math.cos(math.radians(avg_hp - 30))
         + 0.24 * math.cos(math.radians(2 * avg_hp))
         + 0.32 * math.cos(math.radians(3 * avg_hp + 6))
         - 0.20 * math.cos(math.radians(4 * avg_hp - 63)))
    d_ro = 30 * math.exp(-(((avg_hp - 275) / 25) ** 2))
    Rc = 2 * math.sqrt(avg_Cp ** 7 / (avg_Cp ** 7 + 25 ** 7)) if avg_Cp else 0.0
    Sl = 1 + (0.015 * (avg_Lp - 50) ** 2) / math.sqrt(20 + (avg_Lp - 50) ** 2)
    Sc = 1 + 0.045 * avg_Cp
    Sh = 1 + 0.015 * avg_Cp * T
    Rt = -math.sin(math.radians(2 * d_ro)) * Rc
    return math.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2
                     + Rt * (dCp / Sc) * (dHp / Sh))


def delta_e(expected, actual):
    c1, c2 = parse_color(expected), parse_color(actual)
    if c1 is None or c2 is None:
        return None
    return ciede2000(rgb_to_lab(c1), rgb_to_lab(c2))


def main(argv):
    threshold = None
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == "--threshold":
            try:
                threshold = float(argv[i + 1])
            except (IndexError, ValueError):
                sys.stderr.write("color_delta: --threshold needs a numeric value\n")
                return 2
            i += 2
        else:
            args.append(argv[i])
            i += 1
    if len(args) != 2:
        sys.stderr.write("usage: color_delta.py [--threshold T] <expected> <actual>\n")
        return 2
    de = delta_e(args[0], args[1])
    if de is None:
        sys.stderr.write("color_delta: unparseable color(s)\n")
        return 2
    print(f"{de:.2f}")
    if threshold is not None:
        return 0 if de <= threshold else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
