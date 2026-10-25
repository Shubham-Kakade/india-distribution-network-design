# India Distribution Network Design — Project Brief

**Purpose:** Portfolio project for the Cushman & Wakefield Supply Chain & Logistics Advisory (SCLA) Analytics team, Kochi/Bangalore (Senior Analyst target; Senior Consultant stretch).
**Owner:** Shubham Kakade | **Created:** 25 Oct 2026 | **Status:** Spec v2 ready; build not started

> **Read `docs/BUILD_SPEC_v2.md` before building.** It supersedes sections 3, 4 and 9 of this brief where they conflict (data defects, demand model, inbound leg, inventory, service radius, as-is baseline, scenarios, agent design, phase prompts). All parameters are populated in `data/assumptions.yaml`.

---

## 1. The target role (why this project exists)

Posted on LinkedIn by Arun Sridharan (C&W SCLA), apply by DM with CV.
- **Senior Consultant (6–8 yrs):** leads client engagements end to end, mentors the team.
- **Analyst / Senior Analyst (0–5 yrs):** data, modelling and scenario analysis on client projects.
- **Must have:** supply chain network modelling (AIMMS, Coupa/LLamasoft, Optilogic or **Python**), client communication, stakeholder management.
- **Good to have:** exposure to **agentic AI in supply chain optimisation**.

SCLA answers three client questions: **where to locate, how many sites to run, how product should flow**, combining network modelling with real estate expertise. This project answers exactly those three questions for a hypothetical Indian occupier, and closes the main gap on Shubham's profile (no network-modelling work to show).

## 2. The business case (framing for the write-up)

A hypothetical national FMCG / consumer-durables brand serves demand across ~100–150 Indian cities from an ad-hoc set of warehouses. Leadership asks: *How many distribution centres should we run, where, and which cities should each serve, to minimise total landed cost while meeting a next-day service target? How robust is that answer to growth, disruption and fuel shocks?*

## 3. Data

| Input | Source | Notes |
|---|---|---|
| Demand nodes | Kaggle "Top 500 Indian Cities" (zed9941) or GitHub `recurze/IndianCities` | Population + lat/long; demand = population × per-capita consumption assumption |
| Candidate DC sites | Major logistics clusters (see §3.1) | ~10–12 candidates |
| DC fixed cost | Warehouse rents (see §3.1) × DC size + fixed opex | Ties real-estate data into the model, which is the C&W angle |
| Transport cost | ₹/tonne-km road FTL assumption × road distance | Road distance ≈ haversine × 1.3 circuity factor |
| Service level | Distance threshold (e.g. ≤ 500 km ≈ next-day by road) | Constraint: ≥ X% of demand within threshold |

All assumptions live in one editable file (`data/assumptions.yaml`) so every scenario is transparent.

### 3.1 Warehouse rent research already gathered (₹/sq ft/month, Grade A)

| Cluster | Rent | Source |
|---|---|---|
| Bengaluru – Hoskote | 25–27 | Knight Frank India Warehousing Market Report 2025 |
| Bengaluru – Hosur (Attibele–Bommasandra) | 22–26 | Knight Frank 2025 |
| Chennai – Sriperumbudur / Oragadam | 26–28 | Knight Frank 2025 |
| Hyderabad – Medchal | 22–24 | Knight Frank 2025 |
| Hyderabad – Shamshabad | 22–26 | Knight Frank 2025 |
| Ahmedabad – Changodar | 22–25 | Knight Frank 2025 |
| Ahmedabad – Sanand | 23–27 | Knight Frank 2025 |
| Mumbai – Bhiwandi | ~22 (actual deal) | DHL lease, 4.18 lakh sq ft, Nov 2025 (Business Standard) |
| Pune – Chakan | **to verify** | City-wide indicative ₹20–42 (broker blog), needs a better source |
| Delhi NCR – Farrukhnagar / Luhari | **to verify** | Manesar ₹22–38 (broker blog), needs a better source |
| Kolkata – Dankuni | **to verify** | City-wide ₹14–32 (broker blog), needs a better source |
| Nagpur (central hub option) | **to verify** | City-wide ₹8–18 (broker blog) |

**Still to source:** road freight ₹/tonne-km (try the DPIIT/NCAER logistics cost study 2025, the TCI–IIM ready reckoner, or the CRISIL Freight Index), and C&W MarketBeat rents for Pune, NCR and Kolkata.

**Market context for the write-up (C&W, H1 2026):** gross leasing in the top 8 cities reached a record 36.2 mn sq ft (+18% YoY). NCR leads with 8.7 mn sq ft, then Chennai 6.1, Pune 5.9, Mumbai 4.7, Bengaluru 4.4. 3PLs are the largest occupier group at 34%.

## 4. What to build: phases and deliverables

| Phase | Build | Output |
|---|---|---|
| **1. Baseline** | Data prep, demand model, distance matrix, demand map, centre-of-gravity analysis | `src/data_prep.py`, `outputs/demand_map.html` |
| **2. Core model** | Capacitated facility location MILP in **PuLP** (CBC solver): binary open/close per DC, single-sourcing of cities, DC capacity, service-level constraint, objective = fixed + transport cost | `src/model.py`, optimal network map |
| **3. Scenarios** | (a) number-of-DCs sweep 2–8 → cost vs service curve; (b) demand +30% growth; (c) disruption: force-close the top DC; (d) diesel +20%; (e) rent sensitivity | `src/scenarios.py`, `outputs/scenario_summary.csv`, charts |
| **4. Agentic layer** | Streamlit app with an LLM agent (Claude API, tool calling). Tools: `run_scenario(params)`, `compare_scenarios()`, `explain_network()`. User asks "what if Hosur shuts for a month?" → agent runs the model and explains the trade-off | `app/streamlit_app.py`, `src/agent.py` |
| **5. Case study** | 2-page consulting-style write-up: problem, approach, recommendation, scenario insights, limitations | `README.md` + `docs/case_study.pdf` |

### Model formulation (Phase 2)
- **Sets:** cities *i*, candidate DCs *j*
- **Decisions:** `y_j ∈ {0,1}` (open DC j), `x_ij ∈ {0,1}` (city i served by DC j)
- **Minimise:** Σ_j F_j·y_j + Σ_ij c·d_ij·D_i·x_ij
- **Subject to:** each city is assigned to exactly one DC; x_ij ≤ y_j; Σ_i D_i·x_ij ≤ Cap_j·y_j; Σ_ij D_i·x_ij·[d_ij ≤ S] ≥ α·ΣD_i; optional Σ y_j = k (for the sweep)

## 5. Folder structure

```
Supply Chain Network Design/
├── PROJECT_BRIEF.md        ← this file
├── README.md               ← public case study (Phase 5)
├── requirements.txt
├── data/raw/               ← downloaded datasets
├── data/processed/         ← cleaned demand, candidates, distance matrix
├── data/assumptions.yaml   ← all cost and service parameters
├── notebooks/              ← exploration (optional)
├── src/                    ← data_prep.py, model.py, scenarios.py, agent.py
├── app/                    ← streamlit_app.py
├── outputs/                ← maps, charts, scenario CSVs
└── docs/                   ← case study, sources
```

## 6. Definition of done
1. One command (`python -m src.scenarios`) reproduces every result from the raw data.
2. A clear recommendation: "Open N DCs at A, B, C; total cost ₹X Cr/yr; Y% of demand within next-day reach," plus the cost-vs-service curve.
3. At least four scenarios with insight written up, not only numbers.
4. A working agentic demo (a screen recording or GIF for the LinkedIn DM).
5. Pushed to GitHub with the README as the case study, and the link ready for the DM to Arun.

## 7. After the build
- **Resume:** create a `Shubham_Kakade_Resume_SCLA` variant. Lead with this project, Python/SQL, the agentic AI platform ownership and client-facing strategy work. Six Sigma Green Belt goes in as supporting evidence of operations thinking.
- **DM to Arun:** short, names the Senior Analyst role, links the GitHub repo and demo.

## 8. Learning plan (run in parallel)
| Track | What to learn |
|---|---|
| Optimisation | LP/MILP basics; transportation problem; uncapacitated and capacitated facility location; PuLP, then Pyomo |
| Network design concepts | Cost-to-serve; greenfield vs baseline vs brownfield studies; service-level trade-offs; inventory pooling (square-root law); single vs multi-sourcing |
| Industry tools | How Coupa Supply Chain Modeler (LLamasoft), Optilogic Cosmic Frog and AIMMS are used; check for free or trial access to one |
| India context | GST-led warehouse consolidation; logistics clusters; PM Gati Shakti and the National Logistics Policy; Grade A warehousing rent and absorption trends (C&W MarketBeat) |
| Interview prep | Walking through a network study end to end; explaining trade-offs to a non-technical client |

## 9. Kick-off prompt for the build session
> Superseded: use the phase-by-phase prompts in `docs/BUILD_SPEC_v2.md` §15, starting with Phase 0.
