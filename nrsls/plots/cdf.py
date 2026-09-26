"""CDF plots (matplotlib is imported by the caller; it is an optional
dependency).

Styling: categorical series take the palette slots in fixed order (blue,
orange, aqua, yellow), 2 px lines, solid hairline grid and recessive axes;
text stays in the ink colours, never the series colour.  Reference curves
are drawn in the primary ink.
"""

from __future__ import annotations

from ..metrics.kpi import ecdf

SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
SEQUENTIAL = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf",
              "#184f95", "#0d366b")
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
LINE_PT = 1.4          # ~2 px at the 130 dpi used for the figures


def style_axes(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.6, ls="-")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=MUTED, labelcolor=INK_2, labelsize=8)
    ax.xaxis.label.set_color(INK_2)
    ax.yaxis.label.set_color(INK_2)
    ax.title.set_color(INK)
    return ax


def plot_cdfs(ax, series: dict, xlabel: str, title: str = "",
              reference: dict | None = None):
    """Plot {label: samples} as CDFs, plus optional {label: (x, cdf)} curves."""
    if len(series) > len(SERIES):
        raise ValueError(f"at most {len(SERIES)} series per panel")
    for color, (label, samples) in zip(SERIES, series.items()):
        x, f = ecdf(samples)
        ax.plot(x, f, color=color, lw=LINE_PT, solid_capstyle="round",
                label=label)
    for label, (x, f) in (reference or {}).items():
        ax.plot(x, f, color=INK, lw=0.9, ls=(0, (4, 2)), label=label)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel("CDF", fontsize=9)
    ax.set_ylim(0, 1)
    if title:
        ax.set_title(title, fontsize=10, loc="left")
    style_axes(ax)
    leg = ax.legend(fontsize=8, frameon=False, loc="lower right")
    for t in leg.get_texts():
        t.set_color(INK_2)
    return ax
