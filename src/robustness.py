"""How robust is the answer (spec §9 S3, R, §16): frontier knee, no-regret sites, k-COG.

Pure functions on solved networks; the scenario runs that feed them live in scenarios.py.
"""

import numpy as np
import pandas as pd

from src.cog import k_centres_of_gravity
from src.config import with_overrides
from src.data_prep import NetworkData
from src.geo import haversine_km
from src.model import Solution, build_and_solve


def knee_alpha(curve: pd.DataFrame) -> float:
    """Knee of one radius's cost-vs-service curve (spec §9 S3; D-028).

    With both axes scaled to 0-1 between the first and last feasible points, the knee is the
    point furthest below the straight line joining them: past it, each further point of service
    costs more than the average point before it (the "Kneedle" rule).
    curve: columns alpha, total (NaN when infeasible).
    """
    feasible = curve.dropna(subset=["total"]).sort_values("alpha")
    x = (feasible["alpha"] - feasible["alpha"].min()) / np.ptp(feasible["alpha"])
    y = (feasible["total"] - feasible["total"].min()) / np.ptp(feasible["total"])
    return float(feasible["alpha"].iloc[int(np.argmax(x - y))])


def site_robustness(
    classify: dict[str, tuple[str, ...]], context: dict[str, tuple[str, ...]]
) -> dict:
    """R: open/closed matrix for every site, and no-regret core vs swing sites (spec §9).

    classify maps scenario id -> open sites for the recommended network and its stress tests:
    the core is open in all of them, swing sites in some. context columns (other service levels,
    forced losses) are shown in the matrix but do not classify (D-030). Pass feasible runs only.
    """
    columns = {**classify, **{k: v for k, v in context.items() if k not in classify}}
    sites = sorted({j for open_dcs in columns.values() for j in open_dcs})
    matrix = pd.DataFrame(
        {sid: [int(j in open_dcs) for j in sites] for sid, open_dcs in columns.items()},
        index=pd.Index(sites, name="dc_id"),
    )
    share = matrix[list(classify)].mean(axis=1)
    return {
        "matrix": matrix,
        "core": sorted(share.index[share == 1]),
        "swing": sorted(share.index[(share > 0) & (share < 1)]),
        "stress_scenarios": list(classify),
    }


def cog_network(params: dict, data: NetworkData, k: int) -> tuple[Solution, np.ndarray]:
    """A k-centre-of-gravity network costed on the same engine as the MILP (§16; D-033).

    Each centre snaps to the nearest candidate whose metro group is still free (heaviest
    cluster first); every zone goes to its nearest chosen site; plant flows come from the MILP
    with that network pinned and no service target. Returns the solution and the centres.
    """
    zones, dcs = data.zones, data.dcs
    centres, labels = k_centres_of_gravity(zones["lat"], zones["lon"], zones["demand_t_yr"], k)
    cluster_t = zones["demand_t_yr"].groupby(labels).sum().sort_values(ascending=False)
    chosen, groups = [], set()
    for c in cluster_t.index:
        km = haversine_km(centres[c, 0], centres[c, 1], dcs["lat"], dcs["lon"])
        for i in np.argsort(km.to_numpy(), kind="stable"):
            if dcs["metro_group"].iloc[i] not in groups:
                chosen.append(dcs["dc_id"].iloc[i])
                groups.add(dcs["metro_group"].iloc[i])
                break
    nearest = data.zone_dc_km[chosen].idxmin(axis=1)
    unconstrained = with_overrides(params, {"service.min_share_within_radius.value": 0.0})
    sol = build_and_solve(unconstrained, data, k=k, forced_open=chosen, fixed_assignment=nearest)
    return sol, centres
