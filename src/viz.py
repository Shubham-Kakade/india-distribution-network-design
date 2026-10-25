"""Maps and charts (spec §12). Inputs arrive in INR Cr; this module never computes a cost.

Charts use one palette (the dataviz reference palette): a single blue ramp, light to dark, for
ordered parts, and the first three categorical slots for series. Every series also differs by
hatch, line style or marker, so each chart still reads in greyscale (spec §12).
"""

from pathlib import Path

import folium
import matplotlib

matplotlib.use("Agg")  # files only, no display
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

MAP_CENTRE_LAT_LON = (22.5, 80.0)
MAP_ZOOM = 5
ZONE_MAX_RADIUS_PX = 22
# Light to dark single hue so the layer mix still reads in greyscale (spec §12)
LAYER_MIX_COLOURS = ["#c6dbef", "#08306b"]


def plot_demand_map(
    zones: pd.DataFrame,
    candidates: pd.DataFrame,
    plants: pd.DataFrame,
    cog_lat_lon: tuple[float, float],
    disclaimer: str,
) -> folium.Map:
    """Demand zones sized by demand and coloured by layer mix, with candidate DCs, plants and
    the demand centre of gravity (spec §12, outputs/demand_map.html)."""
    fmap = folium.Map(location=MAP_CENTRE_LAT_LON, zoom_start=MAP_ZOOM)
    colormap = folium.LinearColormap(
        LAYER_MIX_COLOURS, vmin=0, vmax=1, caption="City-layer share of zone demand"
    )
    colormap.add_to(fmap)

    city_share_frac = zones["city_demand_t_yr"] / zones["demand_t_yr"]
    national_share_frac = zones["demand_t_yr"] / zones["demand_t_yr"].sum()
    # Circle area proportional to demand
    radius_px = ZONE_MAX_RADIUS_PX * np.sqrt(zones["demand_t_yr"] / zones["demand_t_yr"].max())
    zone_layer = folium.FeatureGroup(name="Demand zones")
    # one marker per row: folium has no vectorised marker API
    for zone, city_share, share, radius in zip(
        zones.itertuples(), city_share_frac, national_share_frac, radius_px, strict=True
    ):
        folium.CircleMarker(
            location=(zone.lat, zone.lon),
            radius=radius,
            color=colormap(city_share),
            fill=True,
            fill_opacity=0.75,
            weight=1,
            tooltip=(
                f"{zone.zone_id} {zone.anchor_name} ({zone.state}): "
                f"{zone.demand_t_yr:,.0f} t/yr, {share:.1%} of national; "
                f"city layer {city_share:.0%}"
            ),
        ).add_to(zone_layer)
    zone_layer.add_to(fmap)

    site_layers = [
        ("Candidate DCs", candidates, "dc_id", "darkblue", "warehouse"),
        ("Plants", plants, "plant_id", "red", "industry"),
    ]
    for layer_name, sites, id_col, colour, icon in site_layers:
        layer = folium.FeatureGroup(name=layer_name)
        for site in sites.itertuples():  # small table
            folium.Marker(
                location=(site.lat, site.lon),
                tooltip=f"{getattr(site, id_col)}: {site.name}",
                icon=folium.Icon(color=colour, icon=icon, prefix="fa"),
            ).add_to(layer)
        layer.add_to(fmap)

    folium.Marker(
        location=cog_lat_lon,
        tooltip=f"Demand centre of gravity ({cog_lat_lon[0]:.2f}°N, {cog_lat_lon[1]:.2f}°E)",
        icon=folium.Icon(color="orange", icon="star", prefix="fa"),
    ).add_to(fmap)
    folium.LayerControl().add_to(fmap)
    fmap.get_root().html.add_child(
        folium.Element(
            '<div style="position:fixed;bottom:8px;left:8px;z-index:9999;max-width:460px;'
            'background:white;padding:6px 8px;font:12px sans-serif;border:1px solid #999">'
            "<b>Demand zones, hypothetical client.</b> Census 2011 population shares, MoSPI HCES "
            f"2023-24 consumption index; see data/assumptions.yaml. {disclaimer}</div>"
        )
    )
    return fmap


BLUE_RAMP = ["#cde2fb", "#86b6ef", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
HATCHES = ["", "//", "..", "\\\\", "xx", "--"]
LINE_STYLES = ["-", "--", ":"]
MARKERS = ["o", "s", "^"]
INK, INK_MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e1e0d9", "#fcfcfb"
INCREASE, DECREASE = "#e34948", "#2a78d6"
DPI = 150
FOOTNOTE = (
    "Hypothetical client; illustrative network, not client data. Source: model output "
    "(src/scenarios.py); every parameter, source and confidence in data/assumptions.yaml."
)

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.size": 9,
        "axes.edgecolor": "#c3c2b7",
        "axes.labelcolor": INK_MUTED,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.axisbelow": True,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "hatch.linewidth": 0.6,
    }
)


def save_chart(fig: plt.Figure, path: Path, note: str, disclaimer: str) -> None:
    """Add the chart note, hypothetical-client footnote and disclaimer (spec §12), then save."""
    # Below everything already drawn (rotated tick labels can hang under the figure edge);
    # the tight bounding box then grows to fit the note
    drawn_bottom_in = fig.get_tightbbox(fig.canvas.get_renderer()).y0
    fig.text(
        0.01,
        drawn_bottom_in / fig.get_figheight() - 0.01,
        f"{note}\n{FOOTNOTE}\n{disclaimer}",
        fontsize=6.5,
        color=INK_MUTED,
        va="top",
    )
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)


def plot_cost_curve(sweep_cr: pd.DataFrame, cog_total_cr: pd.Series) -> plt.Figure:
    """S2: annual cost by DC count as stacked components, with the total, its minimum and the
    k-centre-of-gravity network's total for comparison (spec §12, cost_curve.png).

    sweep_cr: index k, one column per component plus "total", INR Cr.
    """
    fig, ax = plt.subplots(figsize=(8, 4.8))
    components = [c for c in sweep_cr.columns if c != "total"]
    bottom = np.zeros(len(sweep_cr))
    for i, comp in enumerate(components):
        ax.bar(
            sweep_cr.index,
            sweep_cr[comp],
            bottom=bottom,
            width=0.7,
            color=BLUE_RAMP[i],
            hatch=HATCHES[i],
            edgecolor=SURFACE,
            linewidth=0.8,
            label=comp.title(),
        )
        bottom += sweep_cr[comp].to_numpy()
    ax.plot(sweep_cr.index, sweep_cr["total"], color=INK, marker="o", lw=1.5, label="Total")
    ax.plot(
        cog_total_cr.index,
        cog_total_cr,
        color=INK_MUTED,
        ls="--",
        marker="s",
        ms=4,
        lw=1.2,
        label="k-centre-of-gravity network (total)",
    )
    k_min = sweep_cr["total"].idxmin()
    ax.annotate(
        f"Minimum: {k_min} DCs, {sweep_cr.loc[k_min, 'total']:.1f}",
        xy=(k_min, sweep_cr.loc[k_min, "total"]),
        xytext=(k_min + 1.5, sweep_cr["total"].max() * 0.8),
        arrowprops={"arrowstyle": "->", "color": INK},
        color=INK,
    )
    ax.set_xticks(sweep_cr.index)
    ax.set_xlabel("Number of DCs (no service constraint)")
    ax.set_ylabel("Annual logistics cost (INR Cr)")
    ax.set_title("Cost by number of DCs (S2)", loc="left", color=INK)
    ax.legend(fontsize=7, ncol=2, frameon=False)
    return fig


def plot_service_frontier(frontier_cr: pd.DataFrame, knee: tuple[int, float, float]) -> plt.Figure:
    """S3: cheapest network cost against the next-day service target, one line per radius, with
    infeasible targets marked and the knee annotated (spec §12, service_frontier.png).

    frontier_cr: columns radius_km, alpha, total (INR Cr, NaN when infeasible).
    """
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for i, (radius_km, grp) in enumerate(frontier_cr.groupby("radius_km")):
        ax.plot(
            100 * grp["alpha"],
            grp["total"],
            color=SERIES[i],
            ls=LINE_STYLES[i],
            marker=MARKERS[i],
            lw=2,
            ms=6,
            label=f"{radius_km} km next-day radius",
        )
        infeasible = grp[grp["total"].isna()]
        if not infeasible.empty:
            ax.annotate(
                f"{radius_km} km: infeasible at "
                + ", ".join(f"{a:.0%}" for a in infeasible["alpha"]),
                xy=(0.02, 0.95 - 0.06 * i),
                xycoords="axes fraction",
                color=INK_MUTED,
                fontsize=8,
            )
    radius_km, alpha, total = knee
    ax.annotate(
        f"Knee: {alpha:.0%} at {radius_km} km, INR {total:.1f} Cr",
        xy=(100 * alpha, total),
        xytext=(100 * alpha - 9, total + 12),
        arrowprops={"arrowstyle": "->", "color": INK},
        color=INK,
    )
    ax.set_xlabel("Share of demand within the radius of its DC (%)")
    ax.set_ylabel("Annual logistics cost (INR Cr)")
    ax.set_title("Price of service: cost-optimal network per target (S3)", loc="left", color=INK)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    return fig


def plot_waterfall(as_is_cr: dict[str, float], recommended_cr: dict[str, float]) -> plt.Figure:
    """As-is total to recommended total, one step per cost component (spec §12).

    Both dicts map component -> INR Cr. Increases are red and hatched, decreases blue.
    """
    fig, ax = plt.subplots(figsize=(8, 4.8))
    as_is_total, rec_total = sum(as_is_cr.values()), sum(recommended_cr.values())
    labels, running = ["As-is"], as_is_total
    ax.bar(0, as_is_total, color=INK_MUTED, width=0.6)
    ax.text(0, as_is_total, f"{as_is_total:.1f}", ha="center", va="bottom", color=INK)
    for i, comp in enumerate(as_is_cr, start=1):
        delta = recommended_cr[comp] - as_is_cr[comp]
        up = delta > 0
        ax.bar(
            i,
            delta,
            bottom=running,
            width=0.6,
            color=INCREASE if up else DECREASE,
            hatch="//" if up else "",
            edgecolor=SURFACE,
            linewidth=0.8,
        )
        ax.text(
            i, max(running, running + delta), f"{delta:+.1f}", ha="center", va="bottom", color=INK
        )
        running += delta
        labels.append(comp.title())
    ax.bar(len(labels), rec_total, color=INK_MUTED, width=0.6)
    ax.text(len(labels), rec_total, f"{rec_total:.1f}", ha="center", va="bottom", color=INK)
    labels.append("Recommended")
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylim(0, max(rec_total, as_is_total) * 1.08)
    ax.set_ylabel("Annual logistics cost (INR Cr)")
    ax.set_title(
        f"As-is to recommended: saving INR {as_is_total - rec_total:.1f} Cr a year "
        "(grey = totals; red hatched = cost rises; blue = cost falls)",
        loc="left",
        color=INK,
    )
    return fig


def plot_tornado(tornado: pd.DataFrame, base_total_cr: float, base_saving_cr: float) -> plt.Figure:
    """S9: total cost and saving vs as-is at each parameter's range ends (spec §12, tornado.png).

    tornado: one row per parameter with label, low_total, high_total, low_saving, high_saving,
    low_dcs, high_dcs, in INR Cr; sorted by the caller (widest swing first).
    """
    rows = tornado.iloc[::-1]  # widest bar on top
    fig, axes = plt.subplots(1, 2, figsize=(11, 0.42 * len(rows) + 1.6), sharey=True)
    y = np.arange(len(rows))
    panels = [
        ("total", base_total_cr, "Total cost (INR Cr)"),
        ("saving", base_saving_cr, "Saving vs as-is (INR Cr)"),
    ]
    for ax, (measure, base, title) in zip(axes, panels, strict=True):
        for end, colour, hatch in (("low", BLUE_RAMP[1], ""), ("high", BLUE_RAMP[4], "//")):
            values = rows[f"{end}_{measure}"].to_numpy()
            ax.barh(
                y,
                values - base,
                left=base,
                color=colour,
                hatch=hatch,
                edgecolor=SURFACE,
                height=0.7,
                label=f"Parameter at {end} end",
            )
        ax.axvline(base, color=INK, lw=1)
        ax.set_title(f"{title}; base {base:.1f}", loc="left", color=INK, fontsize=9)
    for yi, row in zip(y, rows.itertuples(), strict=True):  # small table
        axes[0].text(
            max(row.low_total, row.high_total) + 0.3,
            yi,
            f"DCs {row.low_dcs}/{row.high_dcs}",
            va="center",
            fontsize=7,
            color=INK_MUTED,
        )
    axes[0].set_yticks(y, rows["label"])
    axes[0].legend(frameon=False, fontsize=7, loc="lower right")
    fig.suptitle(
        "Which assumptions matter (S9): re-optimised network at each range end; "
        "DC count shown as low/high",
        x=0.01,
        ha="left",
        color=INK,
    )
    return fig


def plot_site_robustness(open_matrix: pd.DataFrame, n_classifying: int) -> plt.Figure:
    """R: open (dark, marked) or closed (blank) for every site in every scenario (spec §12).

    open_matrix: index dc_id, one column per scenario, values 0/1. The first n_classifying
    columns (recommended network and its stress tests) decide core vs swing; the rest are context.
    """
    fig, ax = plt.subplots(figsize=(0.42 * open_matrix.shape[1] + 3, 0.32 * len(open_matrix) + 1.8))
    ax.imshow(
        open_matrix.to_numpy(),
        cmap=matplotlib.colors.ListedColormap([SURFACE, BLUE_RAMP[4]]),
        aspect="auto",
    )
    for (i, j), is_open in np.ndenumerate(open_matrix.to_numpy()):
        if is_open:
            ax.text(j, i, "●", ha="center", va="center", color="white", fontsize=6)
    ax.set_xticks(
        range(open_matrix.shape[1]), open_matrix.columns, rotation=60, ha="right", fontsize=7
    )
    ax.set_yticks(range(len(open_matrix)), open_matrix.index, fontsize=7)
    ax.set_xticks(np.arange(-0.5, open_matrix.shape[1]), minor=True)
    ax.set_yticks(np.arange(-0.5, len(open_matrix)), minor=True)
    ax.grid(which="minor", color=GRID, lw=0.6)
    ax.grid(which="major", visible=False)
    ax.tick_params(which="minor", length=0)
    ax.axvline(n_classifying - 0.5, color=INK, lw=1.5)
    for x, text, colour in (
        (n_classifying / 2 - 0.5, "recommended + stress tests (classify)", INK),
        ((n_classifying + open_matrix.shape[1]) / 2 - 0.5, "context (do not classify)", INK_MUTED),
    ):
        ax.text(
            x,
            1.01,
            text,
            ha="center",
            va="bottom",
            fontsize=7,
            color=colour,
            transform=ax.get_xaxis_transform(),
        )
    ax.set_title(
        "Site robustness (R): dark cell = site open in that scenario",
        loc="left",
        color=INK,
        pad=18,
    )
    return fig


def plot_rent_headroom(headroom: pd.DataFrame, max_multiplier: float) -> plt.Figure:
    """S7: today's rent against the rent at which each recommended site drops out (spec §12).

    headroom: columns dc_id, rent, switch_rent (NaN when the site survives max_multiplier x rent).
    """
    rows = headroom.sort_values("dc_id", ascending=False)
    y = np.arange(len(rows))
    capped = rows["switch_rent"].isna()
    switch = rows["switch_rent"].fillna(rows["rent"] * max_multiplier)
    fig, ax = plt.subplots(figsize=(8, 0.4 * len(rows) + 1.6))
    ax.barh(
        y,
        switch,
        color=BLUE_RAMP[1],
        hatch="//",
        edgecolor=SURFACE,
        height=0.6,
        label="Rent at which the site drops out",
    )
    ax.barh(y, rows["rent"], color=BLUE_RAMP[4], height=0.6, label="Rent today")
    for yi, s, r, cap in zip(y, switch, rows["rent"], capped, strict=True):
        text = (
            f"> {s:.0f} (stays open at {max_multiplier:.0f}x)"
            if cap
            else f"{s:.1f} (+{s / r - 1:.0%})"
        )
        ax.text(s + 0.5, yi, text, va="center", fontsize=7, color=INK)
    ax.set_yticks(y, rows["dc_id"])
    ax.set_xlabel("Grade A rent (INR per sq ft per month)")
    ax.set_title("Rent headroom per recommended site (S7)", loc="left", color=INK, pad=22)
    ax.legend(frameon=False, fontsize=7, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2)
    ax.set_xlim(0, switch.max() * 1.3)
    return fig


def plot_network_map(
    data, solution, radius_km: float, ring_gc_km: float, title: str, disclaimer: str
) -> folium.Map:
    """One scenario's network: open DCs sized by throughput, assignment lines, next-day rings and
    zones outside the radius highlighted (spec §12, outputs/network_<scenario>.html).

    ring_gc_km is the great-circle radius that corresponds to radius_km by road.
    """
    fmap = folium.Map(location=MAP_CENTRE_LAT_LON, zoom_start=MAP_ZOOM)
    zones = data.zones.set_index("zone_id")
    dcs = data.dcs.set_index("dc_id")
    assigned = solution.assignment[zones.index]
    assigned_km = np.array([data.zone_dc_km.loc[z, j] for z, j in assigned.items()])
    throughput = zones["demand_t_yr"].groupby(assigned).sum()

    lines = folium.FeatureGroup(name="Assignments")
    for z, j in assigned.items():  # one line per zone: folium has no vectorised API
        folium.PolyLine(
            [(zones.loc[z, "lat"], zones.loc[z, "lon"]), (dcs.loc[j, "lat"], dcs.loc[j, "lon"])],
            color="#898781",
            weight=1,
            opacity=0.6,
        ).add_to(lines)
    lines.add_to(fmap)
    rings = folium.FeatureGroup(name=f"{radius_km:.0f} km by road")
    sites = folium.FeatureGroup(name="Open DCs")
    for j in solution.open_dcs:
        folium.Circle(
            (dcs.loc[j, "lat"], dcs.loc[j, "lon"]),
            radius=ring_gc_km * 1000,
            color=BLUE_RAMP[3],
            weight=1,
            fill=False,
            dash_array="4",
        ).add_to(rings)
        folium.CircleMarker(
            (dcs.loc[j, "lat"], dcs.loc[j, "lon"]),
            radius=ZONE_MAX_RADIUS_PX * np.sqrt(throughput.get(j, 0) / throughput.max()) + 3,
            color=BLUE_RAMP[5],
            fill=True,
            fill_opacity=0.85,
            tooltip=f"{j}: {dcs.loc[j, 'name']}, {throughput.get(j, 0):,.0f} t/yr",
        ).add_to(sites)
    rings.add_to(fmap)
    zone_layer = folium.FeatureGroup(name="Zones (orange = beyond next-day radius)")
    for zone, km, dc in zip(zones.itertuples(), assigned_km, assigned, strict=True):
        outside = km > radius_km
        folium.CircleMarker(
            (zone.lat, zone.lon),
            radius=4 if outside else 2.5,
            color=SERIES[1] if outside else INK_MUTED,
            fill=True,
            fill_opacity=0.9,
            tooltip=f"{zone.Index} {zone.anchor_name}: {zone.demand_t_yr:,.0f} t/yr, "
            f"{km:,.0f} km to {dc}",
        ).add_to(zone_layer)
    zone_layer.add_to(fmap)
    sites.add_to(fmap)
    folium.LayerControl().add_to(fmap)
    fmap.get_root().html.add_child(
        folium.Element(
            '<div style="position:fixed;bottom:8px;left:8px;z-index:9999;max-width:520px;'
            'background:white;padding:6px 8px;font:12px sans-serif;border:1px solid #999">'
            f"<b>{title}</b><br>Hypothetical client; illustrative network. {disclaimer}</div>"
        )
    )
    return fmap
