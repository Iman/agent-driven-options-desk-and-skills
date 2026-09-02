"""Dependency-free PNG charts for MCP clients that can display images.

The browser dashboard uses ECharts.  An MCP client cannot see that browser,
so it needs raster images in the tool result itself.  This module draws the
same core market, positioning, and Greek series with the Python standard
library and writes opaque RGB PNG files.
"""

import math
import struct
import zlib


BLACK = (0, 0, 0)
PANEL = (19, 22, 27)
LINE = (48, 54, 64)
GRID = (37, 42, 50)
INK = (236, 239, 244)
MUTED = (154, 162, 175)
CALL = (95, 145, 255)
PUT = (255, 159, 67)
GREEN = (48, 209, 124)
RED = (255, 92, 92)
AMBER = (251, 191, 36)


# A compact 5 by 7 font keeps image export dependency-free.  Lower-case text
# is rendered as upper-case so every label has a defined glyph.
_FONT = {
    " ": ("00000",) * 7,
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00110", "00100"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "%": ("11001", "11010", "00100", "01000", "10110", "00110", "00000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "=": ("00000", "11111", "00000", "11111", "00000", "00000", "00000"),
}


class Canvas:
    """Small RGB raster with the primitives used by the chart panels."""

    def __init__(self, width, height, colour=BLACK):
        self.width = width
        self.height = height
        self.pixels = bytearray(bytes(colour) * (width * height))

    def pixel(self, x, y, colour):
        x, y = int(x), int(y)
        if 0 <= x < self.width and 0 <= y < self.height:
            at = (y * self.width + x) * 3
            self.pixels[at:at + 3] = bytes(colour)

    def rect(self, x, y, width, height, colour):
        left = max(0, int(x))
        top = max(0, int(y))
        right = min(self.width, int(x + width))
        bottom = min(self.height, int(y + height))
        if right <= left or bottom <= top:
            return
        row = bytes(colour) * (right - left)
        for py in range(top, bottom):
            at = (py * self.width + left) * 3
            self.pixels[at:at + len(row)] = row

    def line(self, x0, y0, x1, y1, colour, width=1, dotted=False):
        x0, y0, x1, y1 = map(int, (x0, y0, x1, y1))
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
        error = dx + dy
        step = 0
        while True:
            if not dotted or (step // 4) % 2 == 0:
                half = max(0, width // 2)
                self.rect(x0 - half, y0 - half, width, width, colour)
            if x0 == x1 and y0 == y1:
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                x0 += sx
            if twice <= dx:
                error += dx
                y0 += sy
            step += 1

    def text(self, x, y, value, colour=INK, scale=1):
        cursor = int(x)
        for character in str(value).upper():
            glyph = _FONT.get(character, _FONT[" "])
            for row, bits in enumerate(glyph):
                for column, bit in enumerate(bits):
                    if bit == "1":
                        self.rect(cursor + column * scale,
                                  int(y) + row * scale,
                                  scale, scale, colour)
            cursor += 6 * scale

    def png(self):
        """Encode as an opaque RGB PNG."""
        stride = self.width * 3
        raw = bytearray()
        for row in range(self.height):
            raw.append(0)
            start = row * stride
            raw.extend(self.pixels[start:start + stride])

        def chunk(kind, data):
            return (struct.pack(">I", len(data)) + kind + data
                    + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))

        header = struct.pack(">IIBBBBB", self.width, self.height,
                             8, 2, 0, 0, 0)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                + chunk(b"IEND", b""))


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _compact(value):
    value = float(value)
    absolute = abs(value)
    if absolute >= 1e9:
        return "{:.1f}B".format(value / 1e9)
    if absolute >= 1e6:
        return "{:.1f}M".format(value / 1e6)
    if absolute >= 1e3:
        return "{:.1f}K".format(value / 1e3)
    if absolute >= 10:
        return "{:.0f}".format(value)
    return "{:.2f}".format(value)


def _normalise_series(series):
    clean = []
    for name, colour, points in series:
        values = []
        for x, y in points:
            x, y = _finite(x), _finite(y)
            if x is not None and y is not None:
                values.append((x, y))
        if values:
            clean.append((name, colour, sorted(values)))
    return clean


def _panel(canvas, bounds, title, series, kind="line", spot=None,
           percent=False):
    """Draw one chart with axes, grid, ticks, legend, and a spot marker."""
    x, y, width, height = bounds
    canvas.rect(x, y, width, height, PANEL)
    canvas.rect(x, y, width, 1, LINE)
    canvas.rect(x, y + height - 1, width, 1, LINE)
    canvas.rect(x, y, 1, height, LINE)
    canvas.rect(x + width - 1, y, 1, height, LINE)
    canvas.text(x + 16, y + 14, title, INK, 2)

    series = _normalise_series(series)
    if not series:
        canvas.text(x + 20, y + height // 2, "NO DATA", MUTED, 2)
        return

    all_points = [point for _name, _colour, points in series for point in points]
    x_values = [point[0] for point in all_points]
    y_values = [point[1] for point in all_points]
    x_min, x_max = min(x_values), max(x_values)
    y_min, y_max = min(y_values), max(y_values)
    if kind == "bar":
        y_min, y_max = min(0.0, y_min), max(0.0, y_max)
    if x_min == x_max:
        x_min, x_max = x_min - 1.0, x_max + 1.0
    if y_min == y_max:
        pad = abs(y_min) * 0.1 or 1.0
        y_min, y_max = y_min - pad, y_max + pad
    y_pad = (y_max - y_min) * 0.08
    y_min, y_max = y_min - y_pad, y_max + y_pad

    left, right = x + 66, x + width - 18
    top, bottom = y + 56, y + height - 38
    plot_width, plot_height = right - left, bottom - top

    def px(value):
        return left + (value - x_min) / (x_max - x_min) * plot_width

    def py(value):
        return bottom - (value - y_min) / (y_max - y_min) * plot_height

    for index in range(5):
        yy = top + index * plot_height / 4
        value = y_max - index * (y_max - y_min) / 4
        canvas.line(left, yy, right, yy, GRID)
        label = "{:.1f}%".format(value * 100) if percent else _compact(value)
        canvas.text(x + 7, yy - 3, label, MUTED)
    for index in range(5):
        xx = left + index * plot_width / 4
        value = x_min + index * (x_max - x_min) / 4
        canvas.line(xx, top, xx, bottom, GRID)
        canvas.text(xx - 12, bottom + 10, _compact(value), MUTED)

    zero = py(0.0) if y_min <= 0 <= y_max else bottom
    if y_min <= 0 <= y_max:
        canvas.line(left, zero, right, zero, MUTED)

    if spot is not None and x_min <= spot <= x_max:
        canvas.line(px(spot), top, px(spot), bottom, AMBER, dotted=True)
        canvas.text(min(right - 54, px(spot) + 4), top + 5,
                    "SPOT " + _compact(spot), AMBER)

    legend_x = x + width - 16
    for name, colour, _points in reversed(series):
        legend_x -= len(name) * 6 + 24
        canvas.rect(legend_x, y + 19, 12, 5, colour)
        canvas.text(legend_x + 16, y + 18, name, MUTED)

    if kind == "bar":
        distinct_x = sorted(set(point[0] for point in all_points))
        slot = plot_width / max(1, len(distinct_x))
        bar_width = max(1, min(8, int(slot / (len(series) + 1))))
        for series_index, (_name, colour, points) in enumerate(series):
            offset = (series_index - (len(series) - 1) / 2) * bar_width
            for point_x, point_y in points:
                xx = int(px(point_x) + offset)
                yy = py(point_y)
                canvas.rect(xx - bar_width // 2, min(yy, zero),
                            bar_width, max(1, abs(zero - yy)), colour)
    else:
        for _name, colour, points in series:
            previous = None
            for point_x, point_y in points:
                current = (px(point_x), py(point_y))
                if previous is not None:
                    canvas.line(previous[0], previous[1], current[0], current[1],
                                colour, width=2)
                previous = current


def _within_band(rows, spot, band):
    if not band:
        return list(rows)
    return [row for row in rows
            if _finite(row.get("strike")) is not None
            and abs(float(row["strike"]) - spot) <= spot * band]


def _warning_footer(canvas, text):
    """Draw a solid warning strip without transparency."""
    if not text:
        return
    height = 26
    canvas.rect(0, canvas.height - height, canvas.width, height, AMBER)
    canvas.text(18, canvas.height - 17, str(text)[:190], BLACK, 1)


def market_png(chain, exposure=None, width=1200, height=820, band=0.15,
               footer=None):
    """Render positioning, open interest, volume, and volatility smile."""
    canvas = Canvas(width, height)
    symbol = str(chain.get("underlying") or "OPTION DESK")
    expiry = str(chain.get("expiry") or "NO EXPIRY")
    spot = float(chain.get("spot") or 0.0)
    canvas.text(24, 20, "{} MARKET MAP".format(symbol), INK, 3)
    canvas.text(26, 50, "EXPIRY {}  SPOT {}".format(expiry, _compact(spot)),
                MUTED, 1)
    asof = chain.get("spot_asof") or (chain.get("meta") or {}).get("generated_utc")
    if asof:
        canvas.text(730, 27, "DATA " + str(asof)[:25], MUTED, 1)

    contracts = _within_band(chain.get("contracts") or [], spot, band)
    calls = [row for row in contracts if row.get("type") == "call"]
    puts = [row for row in contracts if row.get("type") == "put"]
    rows = _within_band(((exposure or {}).get("exposure") or {}).get("rows") or [],
                        spot, band)

    first_title = "DEALER GAMMA EXPOSURE" if rows else "OPTION MID PRICE"
    first_kind = "bar" if rows else "line"
    if rows:
        first_series = [
            ("CALL GEX", CALL, [(r.get("strike"), r.get("call_gex")) for r in rows]),
            ("PUT GEX", PUT, [(r.get("strike"), r.get("put_gex")) for r in rows]),
        ]
    else:
        first_series = [
            ("CALL", CALL, [(r.get("strike"), r.get("mid")) for r in calls]),
            ("PUT", PUT, [(r.get("strike"), r.get("mid")) for r in puts]),
        ]

    panels = [(24, 78, 564, 344), (612, 78, 564, 344),
              (24, 446, 564, 344), (612, 446, 564, 344)]
    _panel(canvas, panels[0], first_title, first_series, first_kind, spot)
    _panel(canvas, panels[1], "OPEN INTEREST", [
        ("CALL", CALL, [(r.get("strike"), r.get("open_interest")) for r in calls]),
        ("PUT", PUT, [(r.get("strike"), -(r.get("open_interest") or 0)) for r in puts]),
    ], "bar", spot)
    _panel(canvas, panels[2], "SESSION VOLUME", [
        ("CALL", CALL, [(r.get("strike"), r.get("volume")) for r in calls]),
        ("PUT", PUT, [(r.get("strike"), -(r.get("volume") or 0)) for r in puts]),
    ], "bar", spot)
    _panel(canvas, panels[3], "IMPLIED VOLATILITY", [
        ("CALL", CALL, [(r.get("strike"), r.get("iv")) for r in calls]),
        ("PUT", PUT, [(r.get("strike"), r.get("iv")) for r in puts]),
    ], "line", spot, percent=True)
    _warning_footer(canvas, footer)
    return canvas.png()


def greeks_png(ladder, width=1200, height=820, footer=None):
    """Render delta, gamma, theta, and vega from a Greek ladder."""
    canvas = Canvas(width, height)
    symbol = str(ladder.get("underlying") or "OPTION DESK")
    expiry = str(ladder.get("expiry") or "NO EXPIRY")
    spot = float(ladder.get("spot") or 0.0)
    canvas.text(24, 20, "{} GREEK LADDER".format(symbol), INK, 3)
    canvas.text(26, 50, "EXPIRY {}  SPOT {}".format(expiry, _compact(spot)),
                MUTED, 1)
    rows = ladder.get("rows") or []
    calls = [row for row in rows if row.get("type") == "call"]
    puts = [row for row in rows if row.get("type") == "put"]
    panels = [(24, 78, 564, 344), (612, 78, 564, 344),
              (24, 446, 564, 344), (612, 446, 564, 344)]
    for bounds, key in zip(panels, ("delta", "gamma", "theta", "vega")):
        _panel(canvas, bounds, key.upper(), [
            ("CALL", CALL, [(r.get("strike"), r.get(key)) for r in calls]),
            ("PUT", PUT, [(r.get("strike"), r.get(key)) for r in puts]),
        ], "line", spot)
    _warning_footer(canvas, footer)
    return canvas.png()
