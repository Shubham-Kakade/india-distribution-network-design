# Agent demo transcripts (spec §10, Checkpoint D)

The five demo questions from spec §10, asked in order in one conversation. The recommended Bengaluru site is Hosur (BLR_HSR), so question 2 is an operational disruption of BLR_HSR and question 3 is the follow-up ("it" = Hosur), a strategic loss.

Reproduce with `python -m src.agent --offline` (offline) or `python -m src.agent` (live, with `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` set; D-039). Hypothetical client; every figure is an exact evaluator cost in INR Cr a year.

## Offline mode (26 Oct 2026)

Answers come from the pre-computed library (`outputs/agent_library.json`, 20 questions, built with `python -m src.agent_offline` from the same tools the live agent calls). No network and no solver are used.

**Q1. What's our recommended network and what does it cost?**

S3_400km_80: 9 DCs at INR 244.1 Cr a year, 80.1% of demand next-day. Sites: Mumbai - Bhiwandi (MUM_BHW), Delhi NCR - Farrukhnagar (NCR_FRN), Bengaluru - Hosur (Attibele-Bommasandra) (BLR_HSR), Hyderabad - Shamshabad (HYD_SMB), Ahmedabad - Changodar (AMD_CHG), Kolkata - Dankuni (KOL_DNK), Lucknow - Kanpur Road (LKO_KNP), Indore - Pithampur (IDR_PTH), Patna - Bihta (PAT_BHT). Cost by component (INR Cr a year): primary 85.0, secondary 71.4, space 20.2, handling 6.6, inventory 33.9, fixed 27.0; 4.1% of revenue. Busiest sites: Delhi NCR - Farrukhnagar (NCR_FRN) 61,576 t/yr, 20.5% of volume; Bengaluru - Hosur (Attibele-Bommasandra) (BLR_HSR) 56,200 t/yr, 18.7% of volume; Patna - Bihta (PAT_BHT) 39,575 t/yr, 13.2% of volume; Mumbai - Bhiwandi (MUM_BHW) 36,599 t/yr, 12.2% of volume; Hyderabad - Shamshabad (HYD_SMB) 29,354 t/yr, 9.8% of volume.

*offline · tools: explain_network({"scenario_id": "S3_400km_80"}) · grounding: offline · scenarios: S3_400km_80*

**Q2. What if Hosur shuts for a month?**

AG_outage_BLR_HSR_1m: with Bengaluru - Hosur (Attibele-Bommasandra) (BLR_HSR) shut for 1 month(s), the other 8 sites absorb its zones (zones moved to HYD_SMB (14), MUM_BHW (11)). Extra freight runs at INR 35.2 Cr a year, so the outage costs about INR 2.9 Cr, a floor: lost sales and stock stranded in the closed DC are not costed. Next-day coverage falls from 80.1% to 63.4%, and 25 zones (16.7% of demand) lose next-day delivery.

*offline · tools: simulate_disruption({"dc_id": "BLR_HSR", "mode": "operational", "months": 1}) · grounding: offline · scenarios: AG_outage_BLR_HSR_1m*

**Q3. And if we lost it permanently?**

AG_loss_BLR_HSR: 10 DCs at INR 245.4 Cr a year (+1.3 Cr against S3_400km_80), 80.0% of demand next-day. Against the recommended network it opens CHN_SPB, COK_KLM and closes BLR_HSR. Losing Bengaluru - Hosur (Attibele-Bommasandra) (BLR_HSR) for good therefore costs INR 1.3 Cr a year more than the recommended network, once the network is re-optimised without it.

*offline · tools: simulate_disruption({"dc_id": "BLR_HSR", "mode": "strategic"}) · grounding: offline · scenarios: AG_loss_BLR_HSR*

**Q4. Diesel just went up 20%. Should we change anything?**

AG_diesel_20_f9a1ac (diesel_shock_frac = 0.2): 9 DCs at INR 261.3 Cr a year (+17.2 Cr against S3_400km_80), 80.1% of demand next-day. It keeps the recommended sites.

*offline · tools: run_scenario({"name": "diesel_20", "overrides": {"diesel_shock_frac": 0.2}}) · grounding: offline · scenarios: AG_diesel_20_f9a1ac*

**Q5. Which of our assumptions should I worry about most?**

S9_tornado: each uncertain assumption moved to both ends of its range, with the network re-optimised (base S3_400km_80: INR 244.1 Cr, 9 DCs, saving INR 28.5 Cr against today). Widest cost swings:
- annual_volume_tonnes [240000 to 360000]: total INR 202.8 to 286.2 Cr, 9 DCs at both ends, saving INR 28.7 to 28.1 Cr.
- circuity_factor [1.15 to 1.4]: total INR 229.4 to 264.3 Cr, 8 to 11 DCs, saving INR 31.0 to 26.8 Cr.
- primary_ftl_inr_per_tkm [4.3 to 6.5]: total INR 225.5 to 259.7 Cr, 9 DCs at both ends, saving INR 26.0 to 30.4 Cr.
- secondary_inr_per_tkm [7.0 to 11.0]: total INR 228.1 to 260.1 Cr, 9 DCs at both ends, saving INR 31.5 to 25.5 Cr.
- fixed_cost_per_dc_cr_per_yr [1.5 to 4.5]: total INR 230.6 to 257.6 Cr, 9 DCs at both ends, saving INR 19.5 to 37.5 Cr.

*offline · tools: rank_assumptions({}) · grounding: offline · scenarios: S9_tornado*

### Spot check: three numbers against the model outputs

| Answer | Figure in the reply | Source record | Value in the record |
|---|---|---|---|
| Q2 | outage costs about INR 2.9 Cr | `AG_outage_BLR_HSR_1m`, `extra.outage_cost_cr` | 2.933 |
| Q3 | INR 245.4 Cr a year, 1.3 Cr more | `AG_loss_BLR_HSR`, `cost_cr.total` / `extra.penalty_cr_per_yr` | 245.425 / 1.348 |
| Q4 | INR 261.3 Cr a year | `AG_diesel_20_f9a1ac`, `cost_cr.total` | 261.288, identical to the committed `S6_diesel_20` (same sites) |

### Out-of-range overrides are refused

`run_scenario` checks overrides against `assumptions.yaml` before solving (spec §10: no more than 2x the range width beyond the range). The tool returns the message to the model, which explains it:

```
transport.secondary_inr_per_tkm = 30 is refused: the assumptions range is [7, 11] and an override may go at most 2x the range width beyond it, so the accepted values are [0, 19]
diesel_shock_frac = 2.5 is refused: the assumptions range is [0.2, 0.4] and an override may go at most 2x the range width beyond it, so the accepted values are [0, 0.8]
```

## Live mode: verified in Phase 5 on a local machine

Live mode is verified in Phase 5 on Shubham's laptop, with Gemini as the provider through its OpenAI-compatible endpoint and the key in a git-ignored `.env` (D-043). Run `python -m src.agent` there and paste its output here. Until then the live loop is covered by the mocked-client tests in `tests/test_agent.py`: grounding pass, retry and template; the tool-call cap; refusals; the rate-limit and malformed-call fallbacks; and the history rollback.
