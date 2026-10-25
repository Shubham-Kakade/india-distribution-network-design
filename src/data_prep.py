"""Phase 1 pipeline: clean the raw data, build zones and distances, check them (spec §4, §5, §13).

Run from the project root: python -m src.data_prep
"""

import logging

import numpy as np
import pandas as pd

from src.cog import centre_of_gravity
from src.config import PROJECT_ROOT, load_params
from src.demand import build_demand_points, build_zones
from src.geo import haversine_km, road_distance_km
from src.viz import plot_demand_map

logger = logging.getLogger(__name__)

RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
MILLION = 1e6

RAW_COLUMNS = {
    "State": "state",
    "State/UT": "state",
    "State_in_source": "state",
    "District": "district",
    "City": "city",
    "Population": "population",
    "Population_override": "population_override",
    "Latitude": "lat",
    "Longitude": "lon",
}
# spec §4.2: the one mapping from source spellings to the states file and YAML names.
# Ladakh is folded into J&K, which carries the combined Census 2011 population.
STATE_NAME_MAP = {
    "Jammu & Kashmir": "Jammu and Kashmir",
    "Andaman & Nicobar Islands": "Andaman and Nicobar Islands",
    "Andaman and Nicobar": "Andaman and Nicobar Islands",
    "Ladakh": "Jammu and Kashmir",
}
# Districts (2011 names) that became Telangana in 2014; the city file still says Andhra Pradesh
TELANGANA_DISTRICTS = [
    "Adilabad",
    "Nizamabad",
    "Karimnagar",
    "Medak",
    "Hyderabad",
    "Rangareddy",
    "Mahbubnagar",
    "Nalgonda",
    "Warangal",
    "Khammam",
]
CANDIDATE_COLUMNS = ["dc_id", "name", "state", "lat", "lon", "metro_group", "rent_inr_sqft_month"]
PLANT_COLUMNS = ["plant_id", "name", "state", "lat", "lon", "share_frac"]


def read_raw(file_name: str) -> pd.DataFrame:
    """Read a raw or manual-fix CSV with snake_case column names."""
    return pd.read_csv(RAW_DIR / file_name).rename(columns=RAW_COLUMNS)


def normalise_state_names(df: pd.DataFrame) -> pd.DataFrame:
    """Map source state spellings to the canonical names (spec §4.2), logging each change."""
    renamed = df["state"].map(STATE_NAME_MAP)
    for (old, new), n_rows in df.groupby([df["state"], renamed]).size().items():
        logger.info("fix §4.2 state name: %r -> %r (%d rows)", old, new, n_rows)
    return df.assign(state=renamed.fillna(df["state"]))


def drop_excluded_states(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Drop the island territories served by sea or air (demand.excluded_states)."""
    excluded = df["state"].isin(params["demand"]["excluded_states"]["value"])
    logger.info(
        "Excluded states: dropped %d rows, %s people",
        excluded.sum(),
        f"{df.loc[excluded, 'population'].sum():,.0f}",
    )
    return df[~excluded]


def clean_cities(cities: pd.DataFrame, coords_patch: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Apply every §4.2 fix to the city table; one row per (state, city) with valid coordinates."""
    patch = coords_patch[["state", "city", "lat", "lon", "population_override"]]
    out = cities.merge(
        patch, on=["state", "city"], how="left", suffixes=("", "_fix"), validate="many_to_one"
    )
    patched = out["lat_fix"].notna()
    for (state, city), n_rows in out[patched].groupby(["state", "city"]).size().items():
        logger.info("fix §4.2 zero coordinates: %s (%s), %d row(s) patched", city, state, n_rows)
    out.loc[patched, ["lat", "lon"]] = out.loc[patched, ["lat_fix", "lon_fix"]].to_numpy()
    zero = (out["lat"] == 0) | (out["lon"] == 0)
    if zero.any():
        raise ValueError(
            f"Cities with zero coordinates after patch: {out.loc[zero, 'city'].tolist()}"
        )

    gvmc_pop = out.loc[out["city"] == "GVMC", "population"]
    if gvmc_pop.isin(out.loc[out["city"] == "GHMC", "population"]).any():
        logger.warning(
            "§4.2 GVMC population %s equals a GHMC ward row (likely copy error); kept as the "
            "2011 figure is about 1.73 mn",
            f"{gvmc_pop.iloc[0]:,}",
        )

    to_telangana = (out["state"] == "Andhra Pradesh") & out["district"].isin(TELANGANA_DISTRICTS)
    logger.info(
        "fix §4.2 Telangana: %d city rows (%s people) re-mapped from Andhra Pradesh",
        to_telangana.sum(),
        f"{out.loc[to_telangana, 'population'].sum():,}",
    )
    out.loc[to_telangana, "state"] = "Telangana"
    out = normalise_state_names(out)

    duplicated = out.duplicated(["state", "city"], keep=False)
    for (state, city), n_rows in out[duplicated].groupby(["state", "city"]).size().items():
        logger.info(
            "fix §4.2 duplicate rows: %s (%s) x%d collapsed, population summed", city, state, n_rows
        )
    out = out.groupby(["state", "city"], as_index=False).agg(
        district=("district", "first"),
        population=("population", "sum"),
        lat=("lat", "first"),
        lon=("lon", "first"),
        population_override=("population_override", "first"),
    )

    override = out["population_override"].notna()
    for row in out[override].itertuples():  # small table
        logger.info(
            "fix §4.2 population override: %s %s -> %s",
            row.city,
            f"{row.population:,}",
            f"{row.population_override:,.0f}",
        )
    out.loc[override, "population"] = out.loc[override, "population_override"]
    out = drop_excluded_states(out, params)
    return out[["state", "district", "city", "population", "lat", "lon"]].reset_index(drop=True)


def clean_districts(districts: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Districts usable as within-state spatial weights (spec §4.2): numeric population and
    non-zero coordinates. Weights are rescaled within each state by the demand model."""
    out = districts.assign(population=pd.to_numeric(districts["population"], errors="coerce"))
    no_pop = out["population"].isna()
    logger.info(
        "fix §4.2 districts with non-numeric population dropped: %s",
        out.loc[no_pop, "district"].tolist(),
    )
    out = normalise_state_names(out[~no_pop])
    zero = (out["lat"] == 0) | (out["lon"] == 0)
    logger.info(
        "fix §4.2 districts with zero coordinates dropped: %d rows, %s people "
        "(remaining districts are rescaled within their state)",
        zero.sum(),
        f"{out.loc[zero, 'population'].sum():,.0f}",
    )
    out = drop_excluded_states(out[~zero], params)
    return out[["state", "district", "population", "lat", "lon"]].reset_index(drop=True)


def clean_states(
    states: pd.DataFrame, population_patch: pd.DataFrame, params: dict
) -> pd.DataFrame:
    """State population totals with the §4.2 J&K fix; J&K and Ladakh become one demand state."""
    out = normalise_state_names(states[["state", "population"]])
    merged = out.duplicated("state")
    for row in out[merged].itertuples():  # small table
        logger.info(
            "fix §4.2 %s: second source row (%s people) dropped; total set by override below",
            row.state,
            f"{row.population:,}",
        )
    out = out[~merged].merge(
        population_patch[["state", "population_override"]],
        on="state",
        how="left",
        validate="one_to_one",
    )
    override = out["population_override"].notna()
    for row in out[override].itertuples():  # small table
        logger.info(
            "fix §4.2 state population override: %s %s -> %s",
            row.state,
            f"{row.population:,}",
            f"{row.population_override:,.0f}",
        )
    out.loc[override, "population"] = out.loc[override, "population_override"]
    return drop_excluded_states(out[["state", "population"]], params).reset_index(drop=True)


def distance_table(
    origins: pd.DataFrame, origin_id: str, destinations: pd.DataFrame, dest_id: str, params: dict
) -> pd.DataFrame:
    """Long table (origin_id, dest_id, dist_km) of road km for every pair (spec §5).

    Raw road km; the 25 km intra-zone floor is a cost rule applied where cost is computed (§6).
    """
    dist_km = road_distance_km(origins, destinations, params)
    return pd.DataFrame(
        {
            origin_id: np.repeat(origins[origin_id].to_numpy(), len(destinations)),
            dest_id: np.tile(destinations[dest_id].to_numpy(), len(origins)),
            "dist_km": dist_km.ravel(),  # row-major, so it lines up with repeat/tile
        }
    )


def calibration_table(cities: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Model road km against reference road km for the spec §5 city pairs.

    Raises ValueError if any pair is off by more than checks.calibration_tolerance_frac.
    """
    checks = params["checks"]
    pairs = pd.DataFrame(
        checks["calibration_pairs"]["value"], columns=["city_a", "city_b", "reference_km"]
    )
    lookup = cities.drop_duplicates("city", keep=False).set_index("city")
    missing = sorted(set(pairs["city_a"]).union(pairs["city_b"]) - set(lookup.index))
    if missing:
        raise ValueError(f"checks.calibration_pairs: city not found or not unique: {missing}")
    model_km = np.diag(
        road_distance_km(lookup.loc[pairs["city_a"]], lookup.loc[pairs["city_b"]], params)
    )
    out = pairs.assign(model_km=model_km, error_frac=model_km / pairs["reference_km"] - 1)
    out_of_tolerance = out["error_frac"].abs() > checks["calibration_tolerance_frac"]["value"]
    if out_of_tolerance.any():
        raise ValueError(f"Distance calibration failed (spec §5):\n{out[out_of_tolerance]}")
    return out


def print_sanity_report(
    population: dict[str, float],
    zones: pd.DataFrame,
    calibration: pd.DataFrame,
    cog_lat_lon: tuple[float, float],
    candidates: pd.DataFrame,
    n_zero_coords: int,
    params: dict,
) -> None:
    """Print the Checkpoint A sanity report (spec §13)."""
    checks = params["checks"]

    def mark(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    pop_ok = abs(population["error_frac"]) <= checks["population_tolerance_frac"]["value"]
    volume_t_yr = params["company"]["annual_volume_tonnes"]["value"]
    total_t_yr = zones["demand_t_yr"].sum()
    share_frac = zones["demand_t_yr"] / total_t_yr
    max_share_ok = share_frac.max() <= checks["max_zone_share_frac"]["value"]
    proto_lat, proto_lon = checks["prototype_centre_of_gravity"]["value"]
    cog_offset_km = haversine_km(*cog_lat_lon, proto_lat, proto_lon)
    nearest_dc_km = haversine_km(*cog_lat_lon, candidates["lat"], candidates["lon"])
    mean_lat = np.average(zones["lat"], weights=zones["demand_t_yr"])
    mean_lon = np.average(zones["lon"], weights=zones["demand_t_yr"])
    top10 = zones.assign(share=share_frac).nlargest(10, "demand_t_yr")

    lines = [
        "",
        "=" * 78,
        "CHECKPOINT A SANITY REPORT (spec §13)",
        "=" * 78,
        f"[{mark(pop_ok)}] National population {population['cleaned'] / MILLION:,.1f} mn vs "
        f"Census 2011 net of excluded states {population['reference'] / MILLION:,.1f} mn "
        f"({population['error_frac']:+.2%}; tolerance "
        f"{checks['population_tolerance_frac']['value']:.1%})",
        f"[{mark(n_zero_coords == 0)}] Zero coordinates remaining: {n_zero_coords}",
        f"[INFO] Zones: {len(zones)} (spec expects about 158)",
        f"[{mark(np.isclose(total_t_yr, volume_t_yr))}] Demand total {total_t_yr:,.3f} t/yr "
        f"vs {volume_t_yr:,} t/yr",
        f"[{mark(max_share_ok)}] Largest zone {share_frac.max():.2%} of demand "
        f"(limit {checks['max_zone_share_frac']['value']:.0%})",
        f"[INFO] Rest-of-state layer {zones['rest_demand_t_yr'].sum() / total_t_yr:.1%} of demand "
        f"(target {params['demand']['residual_share_target']['value']:.0%})",
        "",
        "Top 10 zones by demand:",
        f"  {'zone':<6}{'anchor':<26}{'state':<18}{'t/yr':>10}{'share':>8}{'city layer':>12}",
    ]
    lines += [
        f"  {z.zone_id:<6}{z.anchor_name:<26}{z.state:<18}{z.demand_t_yr:>10,.0f}"
        f"{z.share:>8.2%}{z.city_demand_t_yr / z.demand_t_yr:>12.0%}"
        for z in top10.itertuples()  # small table
    ]
    lines += [
        "",
        "Distance calibration (spec §5, tolerance "
        f"{checks['calibration_tolerance_frac']['value']:.0%}): all pairs PASS",
        f"  {'pair':<32}{'model km':>10}{'reference km':>14}{'error':>9}",
    ]
    lines += [
        f"  {c.city_a + ' - ' + c.city_b:<32}{c.model_km:>10,.0f}{c.reference_km:>14,}"
        f"{c.error_frac:>9.1%}"
        for c in calibration.itertuples()  # small table
    ]
    lines += [
        "",
        f"[INFO] Demand centre of gravity (Weiszfeld, min tonne-km) {cog_lat_lon[0]:.2f}°N, "
        f"{cog_lat_lon[1]:.2f}°E: {cog_offset_km:,.0f} km from the prototype's {proto_lat}°N, "
        f"{proto_lon}°E; nearest candidate {candidates['dc_id'].iloc[nearest_dc_km.argmin()]} "
        f"at {nearest_dc_km.min():,.0f} km",
        f"[INFO] Demand-weighted mean location {mean_lat:.2f}°N, {mean_lon:.2f}°E",
        "=" * 78,
    ]
    print("\n".join(lines))  # noqa: T201


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    params = load_params()

    raw_states = read_raw("final_states.csv")
    cities = clean_cities(
        read_raw("final_cities.csv"), read_raw("manual_fixes/city_coords_patch.csv"), params
    )
    districts = clean_districts(read_raw("final_districts.csv"), params)
    states = clean_states(raw_states, read_raw("manual_fixes/state_population_patch.csv"), params)

    # Excluded states carry the same names in the raw states file
    excluded = raw_states["state"].isin(params["demand"]["excluded_states"]["value"])
    reference_pop = (
        params["checks"]["census_2011_population"]["value"]
        - raw_states.loc[excluded, "population"].sum()
    )
    population = {
        "cleaned": states["population"].sum(),
        "reference": reference_pop,
        "error_frac": states["population"].sum() / reference_pop - 1,
    }
    if abs(population["error_frac"]) > params["checks"]["population_tolerance_frac"]["value"]:
        raise ValueError(f"National population check failed (spec §4.2): {population}")

    zones = build_zones(build_demand_points(cities, districts, states, params), params)
    candidates = pd.DataFrame(params["candidate_dcs"]).rename(
        columns={"id": "dc_id", "rent": "rent_inr_sqft_month"}
    )[CANDIDATE_COLUMNS]
    plants = pd.DataFrame(params["plants"]["list"]).rename(
        columns={"id": "plant_id", "share": "share_frac"}
    )[PLANT_COLUMNS]
    calibration = calibration_table(cities, params)
    cog_lat_lon = centre_of_gravity(zones["lat"], zones["lon"], zones["demand_t_yr"])

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    tables = {
        "zones": zones,
        "candidates": candidates,
        "plants": plants,
        "dist_zone_dc": distance_table(zones, "zone_id", candidates, "dc_id", params),
        "dist_plant_dc": distance_table(plants, "plant_id", candidates, "dc_id", params),
    }
    for name, table in tables.items():
        table.to_csv(PROCESSED_DIR / f"{name}.csv", index=False)
        logger.info("Wrote data/processed/%s.csv (%d rows)", name, len(table))
    OUTPUTS_DIR.mkdir(exist_ok=True)
    plot_demand_map(
        zones, candidates, plants, cog_lat_lon, params["meta"]["disclaimer"].strip()
    ).save(OUTPUTS_DIR / "demand_map.html")
    logger.info("Wrote outputs/demand_map.html")

    n_zero_coords = int(((cities[["lat", "lon"]] == 0).any(axis=1)).sum())
    print_sanity_report(
        population, zones, calibration, cog_lat_lon, candidates, n_zero_coords, params
    )


if __name__ == "__main__":
    main()
