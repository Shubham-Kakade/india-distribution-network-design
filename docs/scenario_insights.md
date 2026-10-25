# Scenario insights (Phase 3 draft)

Hypothetical client, illustrative network. Every figure is an exact evaluator cost in INR Cr per year, reproduced by `python -m src.scenarios` (outputs in `outputs/scenarios/` and `outputs/scenario_summary.csv`). The recommended network is the base case: 9 DCs at 400 km / 80% next-day, INR 244.1 Cr. Assumptions, sources and confidence are in `data/assumptions.yaml`; scenario conventions are D-027 to D-033 in `docs/DECISIONS.md`.

## Recommended network

**Open 9 DCs: Bhiwandi (Mumbai), Farrukhnagar (NCR), Hosur (Bengaluru), Shamshabad (Hyderabad), Changodar (Ahmedabad), Dankuni (Kolkata), Kanpur Road (Lucknow), Pithampur (Indore) and Bihta (Patna). The network costs INR 244.1 Cr a year (4.1% of revenue), puts 80.1% of demand within 400 km of its DC (99.1% within 900 km), and saves INR 28.5 Cr a year (10.5%) against today's 15 state depots at the same service level.**

The service level is the knee of the 400 km cost-versus-service frontier (S3). Up to 80%, each further five points of next-day coverage costs INR 2.4–3.4 Cr. From 80% to 85% it costs 6.0 Cr, and every step after that costs at least 5 Cr. The R heatmap confirms the choice. Seven of the nine sites (Mumbai, NCR, Bengaluru–Hosur, Hyderabad–Shamshabad, Ahmedabad, Kolkata, Patna) stay open in every stress test of the recommendation: growth, fuel, rents and plant footprint. These seven are the no-regret core to commit to first. Two sites are swing sites, each with a named trigger:
- **Central India, Indore or Nagpur:** Pithampur gives way to Nagpur–MIHAN under demand growth, either fuel shock and the no-Puducherry footprint: Indore wins on rent, Nagpur on freight. It is one central site whose location real-estate diligence should settle.
- **Lucknow:** it drops out only if an eastern plant is added.

One caveat for the reviewer. The knee depends on the 400 km / 85% cell. With the free-run proxy fixed at `k_ref = 6` (D-027), that cell costs 250.1 Cr. A proxy sized for 8–11 DCs finds an 11-DC network at 248.3 Cr, and with that cell the knee rule picks 85% instead (D-028). The 80% recommendation therefore holds by a narrow margin. In a steering committee, the honest framing is "80% is the cost-efficient point; 85% costs about INR 4–6 Cr a year more".

## S0: What does today cost?

The as-is network costs **INR 272.6 Cr a year** with 81.4% of demand next-day. That is almost exactly the recommended network's service level, so the 28.5 Cr saving is a like-for-like comparison, not a trade of service for cost. Today's network runs 15 sites. That buys short last-mile runs (secondary freight 58.6 Cr, against 71.4 Cr recommended), but every other line suffers:
- fixed overhead of 45 Cr, against 27 Cr;
- inventory of 40.9 Cr, because safety stock is split 15 ways;
- primary freight of 96.5 Cr, because depots sit in every state rather than near the plants.

The waterfall (`as_is_vs_recommended.png`) shows the consolidation trade cleanly: fewer, larger DCs give up 12.8 Cr of last-mile freight and save 18.0 Cr of fixed cost, 11.5 Cr of primary freight, 7.1 Cr of inventory and 4.8 Cr of space. The baseline is illustrative (pre-GST state C&F depots, Grade B rents), not observed client data.

## S1: What is the cheapest possible network?

With no service target, the cheapest network has **4 DCs** (Mumbai, NCR, Chennai, Patna) at **INR 231.2 Cr**. It reaches only **49.4%** of demand next-day. The recommended network costs **12.9 Cr (5.6%) more** and lifts next-day coverage by 31 points. That is the price of service: about INR 0.4 Cr a year per point of next-day coverage between the cost optimum and the knee. A client choosing cost alone would be choosing a two-day network for half its market (S1 still reaches 94.7% within 900 km).

## S2: How many DCs?

The cost curve (`cost_curve.png`) bottoms out at 4 DCs (231.2 Cr) and is **flat**: anything from 4 to 9 DCs costs within about 3% of the minimum (231.2 to 238.1 Cr). As DCs are added, secondary freight falls (113.9 Cr at 4 DCs, 83.5 Cr at 9). Fixed cost rises by 3 Cr per site, and inventory rises because the square-root law penalises splitting safety stock. These largely cancel. Cost alone therefore cannot pick the DC count. Service policy picks it (S3), and real-estate diligence picks the swing site. One or two DCs are far worse (465 and 318 Cr), so the decision is "4 to 9", never "1 to 3".

## S3: What does service cost?

The frontier (`service_frontier.png`) prices each service step:
- **400 km:** 70% costs 238.3 Cr (7 DCs), 80% costs 244.1 Cr (9 DCs), 90% costs 255.4 Cr (12 DCs) and 95% costs 264.2 Cr (14 DCs). The last 15 points cost INR 20 Cr a year, more than three times the first 10 (5.8 Cr).
- **300 km** (closer to what an Indian truck covers in a day): service above 80% is **infeasible**. 15% of demand lies more than 300 km from *every* candidate cluster, spread across interior Karnataka and Andhra Pradesh, MP, Rajasthan, Chhattisgarh, West Bengal, J&K and Jharkhand. So the candidate list, not the model, caps 300 km service at 85%, and below that once only one site per metro may open. 80% at 300 km needs 14 DCs and 257.7 Cr.
- **500 km:** 80% is achievable with 7 DCs at 238.4 Cr.

The radius definition is therefore worth INR 6–14 Cr a year at the same 80% target (500 vs 400 km, and 400 vs 300 km): "next-day" must be defined with the client's transport team before the DC count is fixed. A tighter promise would also need new candidate clusters in the under-served interiors, not just more DCs.

## S4: Does growth change the answer?

With demand **+30% uniformly**, the network keeps 9 DCs and eight of the nine sites. Only Pithampur swaps for Nagpur. The total rises to 307.6 Cr, so cost per tonne falls by about 3% (scale economies in fixed cost and safety stock). The **regional-skew** variant (East +45%, Centre +35%, rest +25%) gives the same answer: 9 DCs, the same Nagpur swap, 314.4 Cr. No DC comes near its capacity of about 597,000 t a year (500,000 sq ft maximum): the busiest reaches only 14% of it. Growth up to +30% therefore needs no extra site, and the network design is robust to growth. The Indore-to-Nagpur swap is the recurring pattern of this study. Pithampur wins on rent (INR 18 against 20), Nagpur on freight (it is more central to the plants and to demand). Anything that makes freight weigh more relative to rent tips the choice to Nagpur: more volume, dearer diesel, or a lost plant.

## S5a: What if a site goes down for a month?

The busiest DC is **NCR–Farrukhnagar**. If it is shut for one month and its zones re-assigned to the other eight sites, freight rises at an annualised **INR 28.4 Cr**, so the one-month outage costs about **INR 2.4 Cr**. The larger cost is service. Next-day coverage falls from **80.1% to 64.0%**, and **29 zones** lose next-day delivery, about 48,000 t a year (16% of national demand): Delhi, Gurgaon, Noida, Ghaziabad, Faridabad, Chandigarh, Ludhiana, Dehradun, Jaipur and more. The 20% capacity surge is never needed, because no DC is near capacity. The operational risk is therefore a service risk concentrated in the North, not a cost risk. It argues for a documented North contingency, such as a cross-dock or 3PL overflow agreement in the Rajpura or Jaipur cluster, rather than for a tenth DC.

## S5b: What if we lose the site permanently?

If NCR–Farrukhnagar is lost for good and the network re-optimised, the penalty is only **INR 2.2 Cr a year (0.9%)**, with service held at 80%. The model replaces it with **Rajpura (Punjab)** and moves the central site from Indore to Nagpur. NCR therefore has a credible substitute: losing it strategically is cheap, while losing it operationally (S5a) is not. The real-estate implication is that the NCR lease terms matter more for continuity (break clauses, a landlord with alternative stock) than for price.

## S6: Fuel shock?

A **+20% diesel** price raises freight by 11% and total cost by **17.6 Cr (7.2%)**. **+40%** raises cost by **35.2 Cr (14.4%)**. Neither shock changes the DC count: both keep 9 DCs and swap Pithampur for Nagpur, the same freight-versus-rent swing as in growth. Dearer freight would favour more DCs on cost alone (total freight falls as DCs are added, S2), but at the recommended target the 80% service constraint, not cost, already sets the count at 9. Fuel risk is a budget risk, best hedged with diesel-linked freight contracts, not a network-design risk.

## S7: Real-estate sensitivity?

Moving **every rent ±20%** changes cost by only **±2.8–2.9 Cr (1.2%)** and **no site changes**: warehouse space (rent plus opex) is about 8% of total logistics cost. Rent headroom per site (`rent_headroom.png`, raising one site's rent at a time):
- Kolkata could pay 184% more before it drops out.
- Mumbai 117%, Bengaluru–Hosur 95%, NCR 94%, Ahmedabad 86% and Lucknow 73%.
- Hyderabad–Shamshabad only 38%. Pithampur only **22%**: at about INR 21.9 per sq ft the model moves the central site elsewhere.
- **Patna–Bihta stays open even at three times today's rent.**

This is the C&W angle in one chart. The low-confidence rent for Patna, flagged in spec §3, **does not matter**, because Patna is chosen for its location (the Gangetic plain's demand) whatever it costs. The central-India site is the one where a rent survey would change the answer. It is the first location to send real-estate diligence to.

## S8: Does plant footprint drive the answer?

Plant footprint drives **cost far more than site choice**:
- **No Puducherry plant** (shares renormalised): cost rises by **INR 28.5 Cr (11.7%)**, almost all of it primary freight (+27.8 Cr), because the South is served from Haridwar and Silvassa. The network keeps 9 DCs, with the Indore-to-Nagpur swing.
- **An eastern plant at Uluberia (Howrah)**: cost falls by **INR 33.1 Cr (13.6%)**, almost all in primary freight (85.0 down to 52.4 Cr). Rajpura replaces Lucknow, and Nagpur replaces Indore.

The DC footprint is therefore largely separable from the sourcing decision: the seven core sites survive both variants. The sourcing footprint, though, is worth as much as the whole DC consolidation saving. A next step on a real engagement is to model plant allocation jointly with the network. Both footprints are analyst assumptions (D-031).

## S9: Which assumptions matter?

The tornado (`tornado.png`) re-optimises the network with each low- or medium-confidence parameter at its range ends:
- **Volume** moves total cost most (203–286 Cr), but it scales today's cost too: the saving against the as-is network barely moves (28.1–28.7 Cr).
- **Circuity** (the road-to-straight-line ratio) is the one input that changes the DC count. At 1.15 the model opens 8 DCs; at 1.40 it opens 11. Calibrating it against real road distances (OSRM, spec §5) is the cheapest way to firm up the answer.
- **Freight rates** move cost by about 16–19 Cr either way, and **safety-stock days** (4 to 9) by 27 Cr across the range, without changing the DC count.
- **Fixed cost per DC is the input that matters for the business case.** At INR 1.5 Cr per site, the saving against today falls to **19.2 Cr**; at 4.5 Cr it rises to **37.5 Cr**. This is the question an interviewer will ask first. The consolidation case survives at the low end, but its size depends on an analyst assumption that the client's own overhead data should replace.
- Demand-model parameters (rest-of-state share, elasticity, metro uplift) move cost by less than 10 Cr and never change the site count by more than one.
- The diesel share has no effect without a fuel shock.

## R: Which sites are no-regret?

Across the recommended network and its S4, S6, S7 and S8 stress tests, **seven sites are always open**: Mumbai–Bhiwandi, NCR–Farrukhnagar, Bengaluru–Hosur, Hyderabad–Shamshabad, Ahmedabad–Changodar, Kolkata–Dankuni and Patna–Bihta. These are no-regret commitments. The **swing sites** are Pithampur and Nagpur (one central-India site, location open), Lucknow (displaced only by an eastern plant) and Rajpura (needed only if NCR is lost or the East gets a plant). The context columns (other service levels) show the same core. Chennai replaces Hosur as the southern site in the cost-only network and at 300 km. Kochi, Guwahati, Jaipur and Bhubaneswar enter only with a 300 km radius or at 85% service and above, so they are candidates for a later, higher-service phase rather than for day one.

## Why not just use centre of gravity?

A k-centre-of-gravity network (`cost_curve.png`, dashed line), built by placing k demand-weighted centres, snapping each to the nearest candidate and costing it on the same engine, costs **3–11% more** than the MILP at the same DC count (6.3%, about 15 Cr a year, at 9 DCs). Centre of gravity ignores where the plants are, what each cluster's rent is, and the square-root law, so it sits close to demand but in the wrong places. It is a useful first sketch, but the optimisation earns its cost.

## Limitations to carry into the write-up

- Demand is built from Census 2011 shares and a single aggregated product.
- Zones in Bihar and other rural-heavy states are lumpy: one zone covers 18–36 million people (D-019).
- Distances are haversine × 1.25 rather than real road distances.
- The plants, the as-is network and several rents (Lucknow, Indore, Jaipur, Rajpura, Patna, Kochi, Bhubaneswar) are hypothetical or analyst estimates.
- The 400 km / 85% frontier cell is sensitive to the safety-stock proxy (D-028).
