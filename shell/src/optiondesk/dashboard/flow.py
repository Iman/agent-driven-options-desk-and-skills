"""The pipeline as one figure: which command reads what and writes what.

Drawn as inline SVG in the page's own palette rather than shipped as an
image file, so it renders offline, follows the theme, stays crisp at any
width and can be searched. Every coordinate comes from one grid, so a box
added later lands in line with the others.

The figure shows the artifacts and the commands that write them. The page
itself is not a box: it is the reader of every box, and the caption says
so. Two edges are curves because the graph is not a line: the backtest
reads the same closes as the simulation, and the forward ledger reads a
saved plan rather than the comparison beside it.
"""

import html

BOX_W = 200
BOX_H = 70
GAP = 22
ROW_GAP = 40
LEFT = 10
TOP = 12

# key: (column, row, title, artifact, what the maths is)
NODES = {
    "source": (0, 0, "Provider or your file",
               "quotes, open interest, closes",
               "delayed and third party, or user supplied"),
    "chain": (1, 0, "chain", "chain_SYM_EXPIRY.json",
              "mid quotes; sigma solves BSM = mid"),
    "greeks": (2, 0, "greeks", "greeks_SYM_EXPIRY.json",
               "sixteen analytic Greeks per contract"),
    "exposure": (3, 0, "exposure", "exposure_SYM_EXPIRY.json",
                 "GEX, walls, flip, max pain, smile"),
    "strategy": (1, 1, "strategy", "strategy_SYM_NAME_EXPIRY.json",
                 "legs, payoff, P(profit), friction"),
    "compare": (2, 1, "compare", "comparison_SYM_EXPIRY.json",
                "ranked by E[P/L] / capital at risk"),
    "forward": (3, 1, "forward", "forward_ledger.json",
                "paper positions marked at mid"),
    "closes": (0, 2, "Daily closes", "the underlying's own history",
               "r_t = ln(S_t / S_t-1)"),
    "simulate": (1, 2, "simulate", "simulation_SYM_Nd.json",
                 "GARCH-t posterior, fan, VaR, ES"),
    "backtest": (2, 2, "backtest", "backtest_SYM_STRAT_Nd.json",
                 "modelled premiums, block tests"),
}

# (from, to, label, shape). Straight edges join neighbouring boxes; the
# two curves route under a box that sits between their ends. Horizontal
# edges carry no label: the gap between boxes is narrower than a word.
EDGES = [
    ("source", "chain", "", "right"),
    ("chain", "greeks", "", "right"),
    ("greeks", "exposure", "", "right"),
    ("chain", "strategy", "", "down"),
    ("strategy", "compare", "", "right"),
    ("strategy", "forward", "a saved plan", "under"),
    ("strategy", "simulate", "each plan on every path", "down"),
    ("closes", "simulate", "", "right"),
    ("closes", "backtest", "", "under"),
]

_COLUMNS = 1 + max(node[0] for node in NODES.values())
_ROWS = 1 + max(node[1] for node in NODES.values())
WIDTH = LEFT * 2 + _COLUMNS * BOX_W + (_COLUMNS - 1) * GAP
HEIGHT = TOP + _ROWS * BOX_H + (_ROWS - 1) * ROW_GAP + 44


def _xy(key):
    column, row = NODES[key][0], NODES[key][1]
    return (LEFT + column * (BOX_W + GAP), TOP + row * (BOX_H + ROW_GAP))


def _box(key):
    x, y = _xy(key)
    _, _, title, artifact, what = NODES[key]
    return (
        "<g class='node' data-node='{key}'>"
        "<rect class='box' x='{x}' y='{y}' width='{w}' height='{h}' "
        "rx='9'/>"
        "<text class='t' x='{tx}' y='{y1}'>{title}</text>"
        "<text class='f' x='{tx}' y='{y2}'>{artifact}</text>"
        "<text class='m' x='{tx}' y='{y3}'>{what}</text>"
        "</g>"
    ).format(key=key, x=x, y=y, w=BOX_W, h=BOX_H, tx=x + 12, y1=y + 22,
             y2=y + 41, y3=y + 58, title=html.escape(title),
             artifact=html.escape(artifact), what=html.escape(what))


def _edge(source, target, label, shape):
    sx, sy = _xy(source)
    tx, ty = _xy(target)
    if shape == "right":
        x1, y1 = sx + BOX_W, sy + BOX_H / 2
        x2, y2 = tx, ty + BOX_H / 2
        path = "M {} {} L {} {}".format(x1, y1, x2, y2)
        lx, ly = (x1 + x2) / 2, y1 - 6
    elif shape == "down":
        x1, y1 = sx + BOX_W / 2, sy + BOX_H
        x2, y2 = tx + BOX_W / 2, ty
        path = "M {} {} L {} {}".format(x1, y1, x2, y2)
        lx, ly = x1 + 8, (y1 + y2) / 2 + 4
    else:
        # A U under whatever sits between the two boxes: down from the
        # source's bottom edge, along, and up into the target's bottom.
        depth = ROW_GAP - 10
        x1, y1 = sx + BOX_W - 28, sy + BOX_H
        x2, y2 = tx + BOX_W / 2, ty + BOX_H
        path = "M {} {} C {} {}, {} {}, {} {}".format(
            x1, y1, x1, y1 + depth, x2, y2 + depth, x2, y2)
        # Below the curve's lowest point, which a cubic with these control
        # points reaches at about three quarters of the depth.
        lx, ly = (x1 + x2) / 2, y1 + depth + 9
    out = "<path class='arrow{}' d='{}' marker-end='url(#flowhead)'/>".format(
        " soft" if shape == "under" else "", path)
    if label:
        out += ("<text class='lbl' x='{}' y='{}' text-anchor='middle'>{}"
                "</text>").format(lx, ly, html.escape(label))
    return out


def diagram():
    """The whole figure as one SVG element."""
    parts = [
        "<svg class='flowchart' viewBox='0 0 {} {}' role='img' "
        "aria-label='The commands, the artifacts they write, and which "
        "artifact feeds which'>".format(WIDTH, HEIGHT),
        "<defs><marker id='flowhead' viewBox='0 0 10 10' refX='9' refY='5' "
        "markerWidth='7' markerHeight='7' orient='auto-start-reverse'>"
        "<path class='head' d='M 0 0 L 10 5 L 0 10 z'/></marker></defs>",
    ]
    parts.extend(_edge(*edge) for edge in EDGES)
    parts.extend(_box(key) for key in NODES)
    parts.append("</svg>")
    return "".join(parts)


CAPTION = (
    "Every box is one command and one schema-validated artifact under the "
    "artifact directory; every arrow is a file read from that directory. "
    "This page reads all of them and writes nothing. The simulation and "
    "the backtest read the underlying's own closes rather than the chain, "
    "so they file under the symbol rather than an expiry; the forward "
    "ledger marks a saved plan against later chains. Replaced artifacts "
    "move to archive/<date>/ with a timestamp rather than being "
    "overwritten, and each one carries the same meta block: schema, "
    "timestamp, tool and engine versions, the provider used, a degraded "
    "flag with its reason, and notes. Each section below prints the "
    "arithmetic behind its own panel. Nothing here places an order."
)


def panel():
    """The pipeline panel: figure, hint and caption."""
    return (
        "<div class='panel flow'><h3>How this page was built</h3>"
        "<p class='hint'>One command per box, one artifact per box, and the "
        "arithmetic of each printed in the section that shows it.</p>"
        + diagram()
        + "<p class='assume'>{}</p></div>".format(html.escape(CAPTION))
    )
