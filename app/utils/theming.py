"""Colour helpers so any brand colour the superadmin picks stays readable."""
import re

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def clean_hex(value, default):
    value = (value or "").strip()
    if re.match(r"^#[0-9A-Fa-f]{3}$", value):
        value = "#" + "".join(ch * 2 for ch in value[1:])
    return value.upper() if HEX_RE.match(value) else default


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(h):
    def chan(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(c) for c in hex_to_rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_text(h):
    """Black or white, whichever reads better on the given background."""
    lum = _luminance(h)
    return "#111111" if (lum + 0.05) / 0.05 > 1.05 / (lum + 0.05) else "#FFFFFF"


def mix(h, other, ratio):
    a, b = hex_to_rgb(h), hex_to_rgb(other)
    return "#{:02X}{:02X}{:02X}".format(*(round(x + (y - x) * ratio) for x, y in zip(a, b)))


def brand_palette(brand):
    p = brand.primary_color if brand else "#C8102E"
    s = brand.secondary_color if brand else "#0B0B0B"
    bg = brand.background_color if brand else "#FFFFFF"
    return {
        "primary": p,
        "primary_rgb": ",".join(map(str, hex_to_rgb(p))),
        "on_primary": contrast_text(p),
        "primary_dark": mix(p, "#000000", 0.25),
        "primary_soft": mix(p, "#FFFFFF", 0.88),
        "secondary": s,
        "on_secondary": contrast_text(s),
        "background": bg,
        "on_background": contrast_text(bg),
    }
