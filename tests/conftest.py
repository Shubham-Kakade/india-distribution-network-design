"""Tiny hand-built network shared by the cost, model and baseline tests.

Three zones, three candidate DCs, two plants. D1 and D3 share metro group A, so at most one of
them can open. Distances are chosen so the answers are obvious by inspection:

           D1    D2    D3
    Z1     10   500    40      Z1 sits inside D1's zone (cost uses the 25 km floor)
    Z2    300   100   290
    Z3    600    50   580

Demand is 30k / 60k / 90k t/yr, so no DC falls under the minimum size. Within 400 km, D1 alone
covers Z1 + Z2 = 50% of demand and D2 alone covers Z2 + Z3 = 83%.
"""

import pandas as pd
import pytest

from src.config import load_params
from src.data_prep import NetworkData


@pytest.fixture(scope="session")
def params() -> dict:
    return load_params()


@pytest.fixture
def tiny() -> NetworkData:
    zones = pd.DataFrame(
        {
            "zone_id": ["Z1", "Z2", "Z3"],
            "anchor_name": ["Alpha", "Beta", "Gamma"],
            "state": ["Maharashtra", "Maharashtra", "Gujarat"],
            "lat": [19.0, 20.0, 22.0],
            "lon": [73.0, 75.0, 72.5],
            "demand_t_yr": [30_000.0, 60_000.0, 90_000.0],
        }
    )
    dcs = pd.DataFrame(
        {
            "dc_id": ["D1", "D2", "D3"],
            "name": ["One", "Two", "Three"],
            "state": ["Maharashtra", "Gujarat", "Maharashtra"],
            "lat": [19.05, 22.3, 19.2],
            "lon": [73.05, 72.6, 73.3],
            "metro_group": ["A", "B", "A"],
            "rent_inr_sqft_month": [20.0, 30.0, 25.0],
        }
    )
    plants = pd.DataFrame(
        {
            "plant_id": ["P1", "P2"],
            "name": ["West", "North"],
            "state": ["Maharashtra", "Gujarat"],
            "lat": [19.5, 23.0],
            "lon": [73.5, 72.0],
            "share_frac": [0.6, 0.4],
        }
    )
    zone_dc_km = pd.DataFrame(
        [[10.0, 500.0, 40.0], [300.0, 100.0, 290.0], [600.0, 50.0, 580.0]],
        index=pd.Index(zones["zone_id"]),
        columns=pd.Index(dcs["dc_id"]),
    )
    plant_dc_km = pd.DataFrame(
        [[100.0, 800.0, 120.0], [700.0, 100.0, 690.0]],
        index=pd.Index(plants["plant_id"]),
        columns=pd.Index(dcs["dc_id"]),
    )
    return NetworkData(zones, dcs, plants, zone_dc_km, plant_dc_km)
