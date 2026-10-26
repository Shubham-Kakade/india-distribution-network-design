# Agent demo transcripts (spec §10, Checkpoint D)

The five demo questions from spec §10, asked in order in one conversation. The recommended Bengaluru site is Hosur (BLR_HSR), so question 2 is an operational disruption of BLR_HSR and question 3 is the follow-up ("it" = Hosur), a strategic loss.

Reproduce with `python -m src.agent --offline` (offline) or `python -m src.agent` (live, with `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` set; D-039). Hypothetical client; every figure is an exact evaluator cost in INR Cr a year.

## Offline mode (26 Oct 2026, plain-English answers with details, D-053)

Answers come from the pre-computed library (`outputs/agent_library.json`, 20 questions, built with `python -m src.agent_offline` from the same tools the live agent calls). No network and no solver are used. Each answer has two layers, as in the app. First comes a plain-English answer for a business manager: In short, What changes, Why it costs more or less, What to do, then one line with the main limitation and the source. Underneath (in the app, behind "Show details") is the six-part analytical answer (D-049): a headline, what happens in the network, why, what it means for the client, the assumptions and limits, and the source. Every number in both layers is formatted from a tool result, so each answer passes the grounding check (`tests/test_agent.py` checks all 20).

**Q1. What's our recommended network and what does it cost?**

**In short:** The recommended network uses 9 warehouses, costs about INR 244 Cr a year (about 4% of revenue) and gives about 80% of customers next-day delivery.

**What changes:** Warehouses in Mumbai, Delhi NCR, Bengaluru, Hyderabad, Ahmedabad, Kolkata, Lucknow, Indore and Patna. The busiest serve Delhi NCR and Bengaluru.

**Why it costs this much:** Trucking is the biggest cost. More warehouses shorten delivery trips but add running and stock-holding cost; this set balances the two and meets the next-day target.

**What to do:** Commit first to the warehouses that stay open in every test, and confirm the central-India location (Indore or Nagpur) with a property search.

*Limits: Hypothetical client; road distances and some rents are estimates. Source: S3_400km_80*

*Show details:*

**Headline:** The recommended network runs 9 DCs at INR 244.1 Cr a year (4.1% of revenue) and reaches 80.1% of demand next-day.

**What happens in the network:** Sites: Mumbai - Bhiwandi (MUM_BHW), Delhi NCR - Farrukhnagar (NCR_FRN), Bengaluru - Hosur (BLR_HSR), Hyderabad - Shamshabad (HYD_SMB), Ahmedabad - Changodar (AMD_CHG), Kolkata - Dankuni (KOL_DNK), Lucknow - Kanpur Road (LKO_KNP), Indore - Pithampur (IDR_PTH), Patna - Bihta (PAT_BHT). The busiest are Delhi NCR - Farrukhnagar (20.5% of volume); Bengaluru - Hosur (18.7% of volume).

**Why:** Freight is most of the cost: primary 85.0 Cr (34.8%) and secondary 71.4 Cr (29.3%), set by how far DCs sit from plants and from demand. Inventory (33.9 Cr) and fixed site cost (27.0 Cr) grow with every extra site.

**What it means for the client:** Commit first to the sites that stay open in every stress test; confirm the central-India site (Indore or Nagpur) with real-estate diligence.

**Assumptions and limits:** Hypothetical client; Census-based demand, straight-line distance x circuity, some analyst rents.

**Source:** S3_400km_80

*offline · tools: explain_network({"scenario_id": "S3_400km_80"}) · grounding: offline · scenarios: S3_400km_80*

**Q2. What if Hosur shuts for a month?**

**In short:** If the Bengaluru warehouse (Hosur) shuts for a month, extra trucking costs about INR 2.9 Cr and next-day delivery falls from about 80% to about 63% of customers.

**What changes:** Other warehouses take over its market areas, mainly the Hyderabad warehouse (Shamshabad) and the Mumbai warehouse (Bhiwandi). About 17% of customers lose next-day delivery, in places such as Bengaluru, Chennai and Coimbatore.

**Why it costs more:** These customers are now served from warehouses further away, so delivery trucks drive longer distances.

**What to do:** Plan a back-up near Bengaluru, such as a temporary cross-dock or overflow space, rather than building a spare warehouse.

*Limits: Counts extra trucking only, not lost sales. Source: AG_outage_BLR_HSR_1m*

*Show details:*

**Headline:** Shutting Bengaluru - Hosur (BLR_HSR) for 1 month costs about INR 2.9 Cr in extra freight, and next-day coverage falls from 80.1% to 63.4% while it is shut.

**What happens in the network:** The other 8 sites stay open and absorb its zones: HYD_SMB (14), MUM_BHW (11). 25 zones (16.7% of demand) lose next-day delivery, including Bengaluru, Chennai, Coimbatore, Madurai.

**Why:** Freight runs INR 35.2 Cr a year higher while it is shut: secondary (last-mile) freight +29.0 Cr (more tonne-km on last-mile lanes, e.g. zones served from further away) and primary (plant-to-DC) freight +6.2 Cr. Rent, fixed cost and stock at the closed site keep running, so only the freight is charged.

**What it means for the client:** This is a service risk more than a cost risk: it argues for a documented contingency, such as a cross-dock or third-party overflow deal near the site, rather than a spare DC.

**Assumptions and limits:** The outage counts extra freight only; lost sales and stock stranded in the closed DC are not costed, so the cost is a floor.

**Source:** AG_outage_BLR_HSR_1m

*offline · tools: simulate_disruption({"dc_id": "BLR_HSR", "mode": "operational", "months": 1}) · grounding: offline · scenarios: AG_outage_BLR_HSR_1m*

**Q3. And if we lost it permanently?**

**In short:** Losing the Bengaluru warehouse (Hosur) for good adds about INR 1.3 Cr a year, and next-day delivery still reaches about 80% of customers.

**What changes:** It opens the Chennai warehouse (Sriperumbudur) and the Kochi warehouse (Kalamassery) and closes the Bengaluru warehouse (Hosur). About 2% of customers lose next-day delivery.

**Why it costs more:** Mainly because there are more warehouses to run and warehouse space costs more; this is partly offset because trucking from the factories to the warehouses costs less.

**What to do:** Agree strong lease terms (break clauses, a landlord with other buildings) rather than chasing the lowest rent.

*Limits: Assumes the network is redesigned to keep the same next-day target. Source: AG_loss_BLR_HSR*

*Show details:*

**Headline:** Without Bengaluru - Hosur (BLR_HSR), the re-optimised network costs INR 1.3 Cr a year more than the recommended network (INR 245.4 Cr against INR 244.1 Cr), with next-day service at 80.0% against 80.1%.

**What happens in the network:** It opens Chennai - Sriperumbudur / Oragadam (CHN_SPB), Kochi - Kalamassery / Aluva (COK_KLM) and closes Bengaluru - Hosur (BLR_HSR). 34 zones (22.1% of demand) change DC, mostly to CHN_SPB (18), COK_KLM (11), MUM_BHW (4). 7 zones (2.3% of demand) lose next-day service. 4 zones (2.3% of demand) gain it.

**Why:** The biggest cost moves: primary (plant-to-DC) freight -3.4 Cr (fewer tonne-km on inbound lanes from the plants); fixed site cost +3.0 Cr (more sites to run); warehouse space +1.5 Cr (more or dearer warehouse space).

**What it means for the client:** A permanent loss is manageable because a credible substitute exists; secure lease continuity (break clauses, a landlord with alternative stock) more than a lower rent.

**Assumptions and limits:** Re-optimised without the site at the same next-day target. Hypothetical client; Census-based demand, straight-line distance x circuity, some analyst rents.

**Source:** AG_loss_BLR_HSR

*offline · tools: simulate_disruption({"dc_id": "BLR_HSR", "mode": "strategic"}) · grounding: offline · scenarios: AG_loss_BLR_HSR*

**Q4. Diesel just went up 20%. Should we change anything?**

**In short:** A 20% rise in diesel prices adds about INR 17.2 Cr a year, and next-day delivery still reaches about 80% of customers.

**What changes:** No warehouse opens or closes. No customer changes warehouse.

**Why it costs more:** Diesel is about 55% of trucking cost, so every truck journey costs more on the same routes.

**What to do:** Keep the network; protect the budget with fuel-linked trucking contracts.

*Limits: Only this input changes; everything else is as assumed. Source: AG_diesel_20_000d57*

*Show details:*

**Headline:** With diesel prices up 20.0%, the network costs INR 17.2 Cr a year more than the recommended network (INR 261.3 Cr against INR 244.1 Cr), with next-day service unchanged at 80.1%.

**What happens in the network:** It keeps the recommended sites. No zone changes DC.

**Why:** Diesel is 55.0% of freight cost, so both freight rates rise by a factor of 1.11. The biggest cost moves, because dearer diesel raises the rate per tonne-km on the same lanes: primary (plant-to-DC) freight +9.4 Cr; secondary (last-mile) freight +7.9 Cr.

**What it means for the client:** The network holds: this is a budget risk to manage through contracts, such as diesel-linked freight rates, not a reason to move sites.

**Assumptions and limits:** Re-optimised at the recommended service target with only these inputs changed; everything else as in data/assumptions.yaml.

**Source:** AG_diesel_20_000d57

*offline · tools: run_scenario({"name": "diesel_20", "overrides": [{"key": "diesel_shock_frac", "value": 0.2}]}) · grounding: offline · scenarios: AG_diesel_20_000d57*

**Q5. Which of our assumptions should I worry about most?**

**In short:** Sales volume moves total cost the most, but the running cost per warehouse decides how big the saving is: from about INR 19.5 Cr to about INR 37.5 Cr a year.

**What changes:** Only road distances and demand outside the big cities change the best number of warehouses: between 8 and 11.

**Why it costs more or less:** These inputs are estimates; the model was re-run at both ends of each range to see how much the answer moves.

**What to do:** Check distances on real road routes first, and replace the assumed running cost per warehouse with your own figures.

*Limits: One estimate changed at a time; rents are tested separately. Source: S9_tornado*

*Show details:*

**Headline:** Annual volume moves total cost most (202.8 to 286.2 Cr), but fixed cost per DC decides the business case: the saving against today ranges from 19.5 to 37.5 Cr.

**What happens in the network:** Only road circuity (8 to 11 DCs) and rest-of-state demand share (8 to 9 DCs) change the DC count; every other assumption keeps the 9 DCs.

**Why:** Widest cost swings, each re-optimised at both ends of its range: annual volume 202.8 to 286.2 Cr; road circuity 229.4 to 264.3 Cr; primary freight rate 225.5 to 259.7 Cr. Base: 244.1 Cr, saving 28.5 Cr against today.

**What it means for the client:** Calibrate circuity with real road distances first, and replace fixed cost per DC with the client's own overhead data: they decide the DC count and the size of the business case.

**Assumptions and limits:** One low- or medium-confidence assumption at a time across its range; rents are tested separately.

**Source:** S9_tornado

*offline · tools: rank_assumptions({}) · grounding: offline · scenarios: S9_tornado*

### Spot check: three numbers against the model outputs

| Answer | Figure in the reply | Source record | Value in the record |
|---|---|---|---|
| Q2 | outage costs about INR 2.9 Cr | `AG_outage_BLR_HSR_1m`, `extra.outage_cost_cr` | 2.933 |
| Q3 | INR 245.4 Cr a year; about INR 1.3 Cr more | `AG_loss_BLR_HSR`, `cost_cr.total` / `extra.penalty_cr_per_yr` | 245.425 / 1.348 |
| Q4 | INR 261.3 Cr a year | `AG_diesel_20_000d57`, `cost_cr.total` | 261.288, identical to the committed `S6_diesel_20` (same sites) |

### Out-of-range overrides are refused

`run_scenario` checks overrides against `assumptions.yaml` before solving (spec §10: no more than 2x the range width beyond the range). The tool returns the message to the model, which explains it:

```
transport.secondary_inr_per_tkm = 30 is refused: the assumptions range is [7, 11] and an override may go at most 2x the range width beyond it, so the accepted values are [0, 19]
diesel_shock_frac = 2.5 is refused: the assumptions range is [0.2, 0.4] and an override may go at most 2x the range width beyond it, so the accepted values are [0, 0.8]
```

## Live mode: verified in Phase 5 on a local machine

Live mode is verified in Phase 5 on Shubham's laptop, with Gemini as the provider through its OpenAI-compatible endpoint and the key in a git-ignored `.env` (D-043). Run `python -m src.agent` there and paste its output here. Until then the live loop is covered by the mocked-client tests in `tests/test_agent.py`: grounding pass, retry and template; the tool-call cap; refusals; the rate-limit and malformed-call fallbacks; and the history rollback.
