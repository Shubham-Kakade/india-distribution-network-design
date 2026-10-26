# Scenario insights (Phase 3)

Hypothetical client, illustrative network. Every figure is an exact evaluator cost in INR Cr per year, reproduced by `python -m src.scenarios` (outputs in `outputs/scenarios/` and `outputs/scenario_summary.csv`). The recommended network is the base case: 9 DCs at 400 km / 80% next-day, INR 244.1 Cr. Assumptions, sources and confidence are in `data/assumptions.yaml`; scenario conventions are D-027 to D-038 in `docs/DECISIONS.md`.

## Recommended network

**Open 9 DCs: Bhiwandi (Mumbai), Farrukhnagar (NCR), Hosur (Bengaluru), Shamshabad (Hyderabad), Changodar (Ahmedabad), Dankuni (Kolkata), Kanpur Road (Lucknow), Pithampur (Indore) and Bihta (Patna). The network costs INR 244.1 Cr a year (4.1% of revenue), puts 80.1% of demand within 400 km of its DC (99.1% within 900 km), and saves INR 28.5 Cr a year (10.5%) against today's 15 state depots at the same service level.**

The decision rule is like for like (D-028). Today's network reaches 81.4% of demand next-day, so the recommendation is the cheapest network that meets 80%, the highest frontier target today's network already meets. The saving is then a saving at today's service, not a trade of service for cost. Every step above 80% is a priced upgrade option for the client to choose:

| Target | DCs | Extra cost vs recommended | Extra next-day points | Sites |
|---|---|---|---|---|
| **80% (recommended)** | 9 | — | — | as above |
| 85% | 11 | **+INR 4.4 Cr/yr** | +5 | +Guwahati, +Rajpura, and Nagpur in place of Indore |
| 90% | 12 | +INR 11.3 Cr/yr | +10 | +Chennai, +Kochi, +Guwahati, +Jaipur, +Nagpur, +Rajpura; −NCR, −Hosur, −Indore |
| 95% | 14 | +INR 20.1 Cr/yr | +15 | +Bhubaneswar, +Kochi, +Guwahati, +Jaipur, +Nagpur, +Rajpura; −NCR |

**Upgrade option: +2 DCs (Guwahati and Rajpura), +INR 4.4 Cr a year for +5 points of next-day coverage.** The 85% network also moves the central site from Indore to Nagpur. Each further five points costs more than the last (6.9 Cr from 85% to 90%, 8.8 Cr from 90% to 95%).

The "Kneedle" knee of the 400 km frontier (the point furthest below the line joining its ends) is at **85%**. It is reported for reference, not used to decide: it is sensitive to small cost differences between neighbouring cells, and how much service to buy is the client's choice. The knee says that 85% is the last step before the price per point climbs steeply, which is why it is the first upgrade to put in front of the client.

**Staging.** The recommendation can be built in three steps:
1. **7 no-regret sites now:** Mumbai, NCR, Bengaluru–Hosur, Hyderabad–Shamshabad, Ahmedabad, Kolkata and Patna. They stay open in every stress test (see R).
2. **9 sites for 80%:** add Lucknow and one central-India site.
3. **11 sites for 85%:** add Guwahati and Rajpura.

Beyond 85% the network re-shapes rather than grows: the 90% and 95% networks serve Delhi from Jaipur and Rajpura and close NCR–Farrukhnagar, a core site, and the 90% network also swaps Hosur for Chennai. A client who might go above 85% should treat that as a separate network decision, not a further stage.

The 85% network does **not** contain all nine recommended sites: it uses Nagpur, not Indore, as the central site. Nagpur at 80% costs **+INR 0.3 Cr a year** (244.4 Cr, run `S3_400km_80_staged`). With Nagpur in place, the 85% upgrade only adds sites (Guwahati and Rajpura), so nothing built for step 2 is closed in step 3. If the client expects to buy the upgrade, choosing Nagpur now is worth 0.3 Cr a year. If it does not, Indore is the cheaper central site. Nagpur is also the central site the model picks under +30% growth, the +40% diesel shock, the loss of the Puducherry plant and an eastern plant (S4, S6, S8), so it is the more robust of the two.

A note on method. Every free solve now runs twice (D-034): once with the safety-stock proxy sized for 6 DCs, and again with the proxy sized for the number of DCs the first pass opened. The solution with the lower exact cost is kept, and both passes are recorded in each scenario JSON. This replaced a single-pass solve that had mis-priced the 85% cell (250.1 Cr with 10 DCs, against 248.5 Cr with 11). The base case is the same 244.1 Cr network under either pass.

## S0: What does today cost?

The as-is network costs **INR 272.6 Cr a year** with 81.4% of demand next-day. That is almost exactly the recommended network's service level, so the 28.5 Cr saving is a like-for-like comparison, not a trade of service for cost. Today's network runs 15 sites. That buys short last-mile runs (secondary freight 58.6 Cr, against 71.4 Cr recommended), but every other line suffers:
- fixed overhead of 45 Cr, against 27 Cr;
- inventory of 40.9 Cr, because safety stock is split 15 ways;
- primary freight of 96.5 Cr, because depots sit in every state rather than near the plants.

The waterfall (`as_is_vs_recommended.png`) shows the consolidation trade cleanly: fewer, larger DCs give up 12.8 Cr of last-mile freight and save 18.0 Cr of fixed cost, 11.5 Cr of primary freight, 7.1 Cr of inventory and 4.8 Cr of space. The baseline is illustrative (pre-GST state C&F depots, Grade B rents), not observed client data.

## S1: What is the cheapest possible network?

With no service target, the cheapest network has **4 DCs** (Mumbai, NCR, Chennai, Patna) at **INR 231.2 Cr**. It reaches only **49.4%** of demand next-day. The recommended network costs **12.9 Cr (5.6%) more** and lifts next-day coverage by 31 points: about INR 0.4 Cr a year per point. A client choosing cost alone would be choosing a two-day network for half its market (S1 still reaches 94.7% within 900 km).

## S2: How many DCs?

The cost curve (`cost_curve.png`) bottoms out at 4 DCs (231.2 Cr) and is **flat**: anything from 4 to 9 DCs costs within about 3% of the minimum (231.2 to 238.1 Cr). As DCs are added, secondary freight falls (113.9 Cr at 4 DCs, 83.5 Cr at 9). Fixed cost rises by 3 Cr per site, and inventory rises because the square-root law penalises splitting safety stock. These largely cancel. Cost alone therefore cannot pick the DC count. Service policy picks it (S3), and real-estate diligence picks the swing site. One or two DCs are far worse (465 and 318 Cr), so the decision is "4 to 9", never "1 to 3".

## S3: What does service cost?

The frontier (`service_frontier.png`) prices each service step:
- **400 km:** 70% costs 238.3 Cr (7 DCs), 75% 240.7 Cr (8), 80% 244.1 Cr (9), 85% 248.5 Cr (11), 90% 255.4 Cr (12) and 95% 264.2 Cr (14). The steps cost 2.4, 3.4, 4.4, 6.9 and 8.8 Cr: each five points costs more than the one before.
- **300 km** (closer to what an Indian truck covers in a day): service above 80% is **infeasible**. 15% of demand lies more than 300 km from *every* candidate cluster, spread across interior Karnataka and Andhra Pradesh, MP, Rajasthan, Chhattisgarh, West Bengal, J&K and Jharkhand. So the candidate list, not the model, caps 300 km service at 85%, and below that once only one site per metro may open. 70% at 300 km already needs 11 DCs (247.2 Cr); 80% needs 14 DCs and 257.7 Cr.
- **500 km:** 80% is achievable with 7 DCs at 238.4 Cr.

The radius definition is therefore worth INR 6–14 Cr a year at the same 80% target (500 vs 400 km, and 400 vs 300 km): "next-day" must be defined with the client's transport team before the DC count is fixed. A tighter promise would also need new candidate clusters in the under-served interiors, not just more DCs.

## S4: Does growth change the answer?

With demand **+30% uniformly**, the network keeps 9 DCs and eight of the nine sites. Only Pithampur swaps for Nagpur. The total rises to 307.6 Cr, so cost per tonne falls by about 3% (scale economies in fixed cost and safety stock). The **regional-skew** variant (East +45%, Centre +35%, rest +25%) gives the same answer: 9 DCs, the same Nagpur swap, 314.2 Cr. No DC comes near its capacity of about 597,000 t a year (500,000 sq ft maximum): the busiest reaches only 14% of it. Growth up to +30% therefore needs no extra site, and the network design is robust to growth. The Indore-to-Nagpur swap is the recurring pattern of this study. Pithampur wins on rent (INR 18 against 20), Nagpur on freight (it is more central to the plants and to demand). Anything that makes freight weigh more relative to rent tips the choice to Nagpur: more volume, much dearer diesel, or a lost plant.

## S5a: What if a site goes down for a month?

The busiest DC is **NCR–Farrukhnagar**. If it is shut for one month and its zones re-assigned to the other eight sites, freight rises at an annualised **INR 28.4 Cr**, so the one-month outage costs about **INR 2.4 Cr**. The model does not cost lost sales or stock stranded in the closed DC, so the 2.4 Cr is a floor, and the service drop is the real headline. Next-day coverage falls from **80.1% to 64.0%**, and **29 zones** lose next-day delivery, about 48,000 t a year (16% of national demand): Delhi, Gurgaon, Noida, Ghaziabad, Faridabad, Chandigarh, Ludhiana, Dehradun, Jaipur and more. The 20% capacity surge is never needed, because no DC is near capacity. The operational risk is therefore a service risk concentrated in the North, not a cost risk. It argues for a documented North contingency, such as a cross-dock or 3PL overflow agreement in the Rajpura or Jaipur cluster, rather than for a tenth DC.

## S5b: What if we lose the site permanently?

If NCR–Farrukhnagar is lost for good and the network re-optimised, the penalty is only **INR 2.2 Cr a year (0.9%)**, with service held at 80%. The model replaces it with **Rajpura (Punjab)** and moves the central site from Indore to Nagpur. NCR therefore has a credible substitute: losing it strategically is cheap, while losing it operationally (S5a) is not. The real-estate implication is that the NCR lease terms matter more for continuity (break clauses, a landlord with alternative stock) than for price.

## S6: Fuel shock?

A **+20% diesel** price raises total cost by **17.2 Cr (7.1%)** with **no site change**. **+40%** raises cost by **34.9 Cr (14.3%)** and swaps Pithampur for Nagpur, the same freight-versus-rent swing as in growth. Neither shock changes the DC count. Dearer freight would favour more DCs on cost alone (total freight falls as DCs are added, S2), but at the recommended target the 80% service constraint, not cost, already sets the count at 9. Fuel risk is a budget risk, best hedged with diesel-linked freight contracts, not a network-design risk.

## S7: Real-estate sensitivity?

Moving **every rent ±20%** changes cost by only **±2.8–2.9 Cr (1.2%)** and **no site changes**: warehouse space (rent plus opex) is about 8% of total logistics cost. Rent headroom per site (`rent_headroom.png`, raising one site's rent at a time):
- **Kolkata and Patna–Bihta stay open even at three times today's rent.**
- Mumbai could pay 127% more before it drops out; Bengaluru–Hosur 95%, NCR 94%, Ahmedabad 88% and Lucknow 73%.
- Hyderabad–Shamshabad only 40% (about INR 33.6 per sq ft). Pithampur only **22%**: at about INR 21.9 per sq ft the model moves the central site elsewhere.

This is the real-estate angle in one chart. The low-confidence rent for Patna, flagged in spec §3, **does not matter**, because Patna is chosen for its location (the Gangetic plain's demand) whatever it costs. The central-India site is the one where a rent survey would change the answer. It is the first location to send real-estate diligence to, and the staging choice (Indore now, or Nagpur toward 85%) depends on it.

## S8: Does plant footprint drive the answer?

Plant footprint drives **cost far more than site choice**:
- **No Puducherry plant** (shares renormalised): cost rises by **INR 28.4 Cr (11.7%)**, almost all of it primary freight (+27.8 Cr), because the South is served from Haridwar and Silvassa. The network keeps 9 DCs, with the Indore-to-Nagpur swing.
- **An eastern plant at Uluberia (Howrah)**: cost falls by **INR 33.1 Cr (13.6%)**, almost all in primary freight (85.0 down to 52.4 Cr). Rajpura replaces Lucknow, and Nagpur replaces Indore.

The DC footprint is therefore largely separable from the sourcing decision: the seven core sites survive both variants. The sourcing footprint, though, is worth as much as the whole DC consolidation saving. A next step on a real engagement is to model plant allocation jointly with the network. Both footprints are analyst assumptions (D-031, accepted at review, D-036).

## S9: Which assumptions matter?

The tornado (`tornado.png`) re-optimises the network with each low- or medium-confidence parameter at its range ends:
- **Volume** moves total cost most (203–286 Cr), but it scales today's cost too: the saving against the as-is network barely moves (28.1–28.7 Cr).
- **Circuity** (the road-to-straight-line ratio) is the one input that changes the DC count. At 1.15 the model opens 8 DCs (229.4 Cr); at 1.40 it opens 11 (264.3 Cr). Calibrating it against real road distances (OSRM, spec §5) is the cheapest way to firm up the answer.
- **Freight rates** move cost by about 16–19 Cr either way, and **safety-stock days** (4 to 9) by 27 Cr across the range, without changing the DC count.
- **Fixed cost per DC is the input that matters for the business case.** At INR 1.5 Cr per site, the saving against today falls to **19.5 Cr**; at 4.5 Cr it rises to **37.5 Cr** (total 230.6–257.6 Cr). This is the question an interviewer will ask first. The consolidation case survives at the low end, but its size depends on an analyst assumption that the client's own overhead data should replace.
- Demand-model parameters (rest-of-state share, elasticity, metro uplift) move cost by 10 Cr or less and never change the site count by more than one.
- The diesel share has no effect without a fuel shock.

## R: Which sites are no-regret?

Across the recommended network and its S4, S6, S7 and S8 stress tests, **seven sites are always open**: Mumbai–Bhiwandi, NCR–Farrukhnagar, Bengaluru–Hosur, Hyderabad–Shamshabad, Ahmedabad–Changodar, Kolkata–Dankuni and Patna–Bihta. These are the no-regret commitments of staging step 1. The **swing sites**, each with a named trigger:
- **Pithampur or Nagpur** (one central-India site): Nagpur wins under +30% growth, the +40% diesel shock, the loss of Puducherry, an eastern plant, and in the 85% upgrade.
- **Lucknow:** displaced only by an eastern plant.
- **Rajpura:** needed only if the East gets a plant (and, outside R, if NCR is lost or the client buys the 85% upgrade).

The context columns (S1, the other service levels and S5b) show where the core stops holding. Chennai joins as a southern site in the cost-only network, at 300 km, at 400 km / 90% and at 500 km up to 75%. Guwahati enters at 400 km from 85%. Kochi, Jaipur and Bhubaneswar enter at 400 km only at 90% or above (or at other radii), and the 400 km networks at 90% and 95% drop NCR–Farrukhnagar. These are candidates for a later, higher-service phase, not for day one.

## Why not just use centre of gravity?

A k-centre-of-gravity network (`cost_curve.png`, dashed line), built by placing k demand-weighted centres, snapping each to the nearest candidate and costing it on the same engine, costs **3–11% more** than the MILP at the same DC count (6.3%, about 15 Cr a year, at 9 DCs). Centre of gravity ignores where the plants are, what each cluster's rent is, and the square-root law, so it sits close to demand but in the wrong places. It is a useful first sketch, but the optimisation earns its cost.

## Limitations to carry into the write-up

- Demand is built from Census 2011 shares and a single aggregated product.
- Zones in Bihar and other rural-heavy states are lumpy: one zone covers 18–36 million people (D-019).
- Distances are haversine × 1.25 rather than real road distances; circuity is the one parameter that moves the DC count (S9).
- The plants, the as-is network and several rents (Lucknow, Indore, Jaipur, Rajpura, Patna, Kochi, Bhubaneswar) are hypothetical or analyst estimates.
- The safety-stock cost in the optimiser is a linear proxy; every reported figure is the exact evaluator cost, and free solves keep the cheaper of two proxy sizings (D-034).
- S5a costs freight only: lost sales and stranded stock are not modelled, so outage costs are floors.
