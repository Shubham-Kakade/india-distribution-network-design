# India distribution network: how many DCs, where, at what cost

*Steering-committee pre-read · hypothetical national FMCG client · all costs in INR Cr a year · October 2026*

## Situation

A national FMCG brand ships 300,000 tonnes a year to 158 demand zones across India. It serves them from 15 legacy state depots, a footprint drawn around pre-GST state tax boundaries. Today's network costs **INR 272.6 Cr a year** and reaches **81.4%** of demand next-day (within 400 km by road).

## Complication and question

GST removed the tax reason for one depot per state, but the footprint stayed. Leadership asks: **which distribution network minimises landed cost while keeping a next-day promise, and how robust is that answer to growth, disruption, fuel and rent?**

## Answer

**Run 9 DCs:** Bhiwandi (Mumbai), Farrukhnagar (NCR), Hosur (Bengaluru), Shamshabad (Hyderabad), Changodar (Ahmedabad), Dankuni (Kolkata), Kanpur Road (Lucknow), Pithampur (Indore) and Bihta (Patna).

| | Today (15 depots) | Recommended (9 DCs) |
|---|---|---|
| Annual logistics cost | 272.6 | **244.1** (4.1% of revenue) |
| Demand reached next-day | 81.4% | **80.1%** |
| Saving | | **28.5 Cr a year (10.5%)** at comparable service |

The recommendation is the cheapest network at today's service level, so the saving is like for like rather than bought with worse service. Fewer, larger DCs give up 12.8 Cr of last-mile freight, but save 18.0 Cr of fixed cost, 11.5 Cr of primary freight, 7.1 Cr of inventory and 4.8 Cr of space.

**Build it in stages:**

1. **Commit now** to 7 no-regret sites (Mumbai, NCR, Hosur, Shamshabad, Ahmedabad, Kolkata, Patna). They stay open in every stress test.
2. **Reach 80% service** by adding Lucknow and one central-India site.
3. **Upgrade to 85%** by adding Guwahati and Rajpura: +INR 4.4 Cr a year for +5 points of next-day coverage. That upgrade uses Nagpur, not Indore, as the central site. Choosing Nagpur at step 2 costs +0.3 Cr a year and makes the upgrade purely additive.

## Three insights

**1. Service has a rising price, and the radius definition matters as much as the target.** The cheapest network (4 DCs, 231.2 Cr) reaches only 49.4% of demand next-day. On the 400 km frontier each further five points costs more than the last: +4.4 Cr from 80% to 85%, +6.9 Cr to 90%, +8.8 Cr to 95%. Above 85% the network re-shapes (NCR closes in favour of Jaipur and Rajpura) rather than grows. With a 300 km promise, nothing above 80% is feasible, because 15% of demand lies more than 300 km from every candidate cluster. "Next-day" must be agreed with the transport team before the DC count is fixed.

**2. Seven sites are robust; the risk is operational, not strategic.** The 7 core sites survive +30% demand growth, ±20% rents, +20% and +40% diesel shocks, and both plant-footprint variants. The only recurring swing is the central site: Indore wins on rent, Nagpur on freight. Losing NCR for good costs just 2.2 Cr a year once the network is re-optimised. A one-month NCR outage, by contrast, costs at least 2.4 Cr in extra freight (lost sales and stranded stock are not costed), and next-day coverage falls from 80.1% to 64.0% across 29 zones. That argues for a documented North contingency, not a tenth DC.

**3. Real estate is a small share of cost, but it decides one site.** Moving every rent ±20% changes total cost by about ±1.2% (±2.8–2.9 Cr), with no site change. Patna and Kolkata stay open even at three times today's rent, so their low-confidence rents do not matter. Indore can absorb only 22% more rent before the model moves the central site, which makes it the first location for a rent survey. For the business case, the assumption to replace with client data is fixed cost per DC: at INR 1.5 to 4.5 Cr per site, the saving ranges from 19.5 to 37.5 Cr a year.

![Cost against next-day service for 300, 400 and 500 km promises (S3)](../outputs/charts/service_frontier.png)

*Figure: annual cost against the share of demand reached next-day, for three definitions of "next-day" (S3). Each point is a re-optimised network.*

## Approach

- **Demand.** Census 2011 population shares, consumption indices and a city/rest-of-state split, aggregated to 158 zones. Road distance is great-circle distance × 1.25 (calibrated within 15% on 7 reference pairs, with North-East routing via Siliguri).
- **Cost engine.** One exact cost engine covers primary and secondary freight, space, handling, square-root-law inventory and fixed cost. Every reported figure comes from it.
- **Optimiser.** A capacitated facility-location MILP (PuLP + CBC) with single sourcing and a next-day service constraint. 83 scenario runs are reproduced by one command from raw data.
- **What-if agent.** Answers questions by running the model; every number in a reply must come from a tool result.

## Limitations

- **Demand:** Census 2011 shares and a single aggregated product.
- **Distances:** straight-line distances × a circuity factor, not real road distances. Circuity is the one parameter that moves the DC count (8 to 11).
- **Hypothetical inputs:** the plants and the as-is network are hypothetical, and several rents (Lucknow, Indore, Jaipur, Rajpura, Patna, Kochi, Bhubaneswar) are analyst estimates.
- **Outage costing:** the outage cost is a floor, because lost sales are not modelled.

## Next steps on a real engagement

1. Client shipment data and SKU-level demand.
2. Actual lane rates and road distances.
3. Overhead per site from the client's books.
4. A site visit for the central-India swing (Indore or Nagpur).
5. C&W MarketBeat availability and rent checks for the low-confidence clusters.
6. Model plant allocation jointly with the network: the sourcing footprint is worth as much as the whole DC consolidation saving (removing the Puducherry plant costs +28.4 Cr; an eastern plant saves 33.1 Cr).

*Independent portfolio project by Shubham Kakade. Not affiliated with or endorsed by Cushman & Wakefield or any client; company and network are hypothetical. Code and full results: github.com/Shubham-Kakade/india-distribution-network-design.*
