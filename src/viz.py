"""Maps and charts (spec §12). Phase 1 needs only the demand map."""

import folium
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
