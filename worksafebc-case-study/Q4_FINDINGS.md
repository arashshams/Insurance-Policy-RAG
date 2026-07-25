# Q4 - General Construction (7210) industry profile and prioritized interventions (20 marks)

**Scope:** Subsector 7210 - General Construction.
**Data sources:** WorkSafeBC Provincial Overview (Report 3079: CU Profile, Costs, Industry Claims Analysis Counts/Costs tabs) and Industry Claim Cost Drivers (Report 3559: benefit-type distribution, health-care-by-program). Data as of 2026-06-30.
**Windows:** 10-year series (2016-2025) for the CU-Profile/cost/recovery trends; the accident/injury/occupation/body-part cost-and-frequency breakdowns are the dashboard's 5-year aggregate (2021-2025); the benefit-type mix and health-care-by-program figures are 10-year cumulative (2016-2025). Windows differ because the dashboards fix them; see Assumptions & Disclaimers.

## Q4a - Industry profile (10 marks)

### Scale and trajectory
7210 is a large, improving-but-still-elevated subsector. Over 2016-2025 the injury rate fell 4.15 -> 2.98 (-28%) and the serious-injury rate 0.87 -> 0.58 (-33%), while exposure (person-years) grew ~33% (159,704 -> 213,005). So the *rate* is falling even as the *worker base* expands. Annual volume is roughly 6,800 STD/LTD/Fatal claims and ~1,300 serious-injury claims. Total claim costs paid rose 157M -> 262M and total work days lost ~322k -> ~373k over the decade.

### What drives the claims - frequency vs severity
The single most useful lens is comparing each hazard's share of claim COUNT against its share of claim COST. To make this explicit I computed a Severity Index = (cost share %) / (frequency share %); >1 means costlier-than-average per claim.

**Accident type (2021-2025):**

| Accident type | Cost share | Freq share | Severity index |
|---|---|---|---|
| Fall from Elevation | 28.0% | 15.7% | 1.78 |
| Motor vehicle incident | 4.4% | 2.3% | 1.91 |
| Overexertion | 15.6% | 23.7% | 0.66 |
| Struck By | 13.3% | 19.2% | 0.69 |
| Fall on Same Level | 7.6% | 8.7% | 0.87 |

Reading: **Falls from elevation are the #1 driver** - they are simultaneously the largest cost bucket (28%) AND a top-3 frequency bucket (15.7%), with a high severity index (1.78). MVIs are rarer but the most severe per event (1.91). Overexertion and struck-by are high-frequency, lower-severity - a volume/ergonomics problem rather than a catastrophic-injury problem.

**Nature of injury (2021-2025):** Fractures are 29.6% of cost but only 11.1% of count (severity index 2.67); amputations index 3.67. High-frequency lower-cost natures are Other Strains (31.7% count / 24.3% cost), Back Strain (16.9% / 8.9%) and Laceration (15.6% / 6.3%). So the cost is concentrated in traumatic fractures/amputations (fall- and machinery-related), while the volume is musculoskeletal strains.

**Source of injury:** Floors, walkways & ground surfaces dominate (29.4% of cost, 19.5% of count) - consistent with the falls story. Building materials/lumber and people (manual handling) follow.

**Body part (by count):** Wrist/fingers/hand (22.3%) and back (17.8%) lead - hand injuries (handtools, struck-by) and back strains (manual handling).

**Occupations:** Cost and volume both concentrate in *construction trades helpers & labourers* and *carpenters* (each ~15% of cost and ~19% of frequency), followed by plumbers and electricians. Roofers/shinglers appear mid-list (reinforcing the roofing/steep-slope focus of Q3).

**Who gets hurt:** Workers aged 25-54 account for ~70% of cost (~$815M of the $1.164B SLF total, 2021-2025).

### Cost structure (benefit mix and health care)
7210's benefit-cost mix (2016-2025 cumulative) is **LTD 35.2%, Health Care 28.4%, STD 24.7%, Other 11.8%**. This is materially more LTD-weighted than the province (where STD is the larger share) - a signature of more serious, longer-duration injuries. Within health care the top programs are Hospitals ($119M), Physicians ($95M), Physiotherapy ($62M), Home Care ($40M), Hearing Aid Providers ($22M) and Drugs & Pharmacies ($20M) - i.e. acute hospital/surgical care (trauma) plus a large rehab (physio/home-care) tail consistent with the LTD skew.

### Recovery and the regulatory footprint
A worsening signal: long-recovery sprains as a share of all sprains climbed 29% -> 35% over the decade, and RTW-beyond-26-weeks counts drifted up - claims are taking longer to close even as frequency falls. On the prevention/enforcement side, 7210 sees ~21,000 inspection reports and ~15,700 orders a year (2025), with ~290 net penalties and ~390 warning letters - a heavily inspected subsector where enforcement activity has risen since 2019.

### External economic outlook
*(Analytical inference - see Assumptions.)* The dashboards contain no macro forecast, so this is framed from the exposure data plus general context: BC construction employment (person-years) grew ~33% over the decade, and continued residential/infrastructure activity implies the exposure base will stay large or grow. The implication for the BOD is that a *rising worker base can mask rate progress in absolute claim counts* - prevention targets should be expressed as rates, and a growing/greener workforce (new entrants) raises onboarding-and-training risk.

## Q4b - Prioritized interventions and success measures (10 marks)

Interventions are ranked by **impact x feasibility** (impact = share of cost/serious-injury addressable; feasibility = maturity of existing controls/regulation and ease of employer adoption). This ranking is the analyst's judgement and is offered for the candidate to adjust.

**Priority 1 - Falls-from-elevation program (highest impact, high feasibility).** Rationale: 28% of cost and 15.7% of frequency, severity index 1.78 - the only hazard that is both high-cost and high-frequency; ground/floor surfaces are the top injury source. Feasibility is high because fall protection is already the most mature regulatory area (Part 11 OHSR, existing WorkSafeBC high-risk-strategy focus, well-defined engineering controls: guardrails, anchors, controlled-access zones, and pre-work fall-protection planning). Highest expected return per dollar.

**Priority 2 - Manual-materials-handling / ergonomics for sprains & strains (high impact on volume and duration, moderate feasibility).** Rationale: overexertion is the #1 frequency accident type (23.7%) and strains/back-strain dominate injury count; crucially the long-recovery sprain share is *rising* (29%->35%), which is what drives the LTD skew and days-lost. Interventions: mechanical lifting aids, material staging/delivery-to-point-of-use, job rotation, and early-intervention/return-to-work physiotherapy to arrest the long-recovery trend. Feasibility moderate - effective but requires sustained behavioural/process change across many small employers.

**Priority 3 - Struck-by and machinery/mobile-equipment controls (targeted severity reduction).** Rationale: struck-by is a top-3 frequency hazard (19.2%) and, together with 'caught in' and MVI, accounts for the traumatic fracture/amputation costs (high severity indices). Interventions: traffic-management/spotter programs, exclusion zones around mobile equipment, tool-tethering and hand-injury controls. Feasibility moderate - site-specific but supported by clear existing standards.

*(Secondary, lower priority: occupational-disease/asbestos exposure control - strategically important for fatalities per Q2c but a different, long-latency time horizon and largely legacy-driven, so it is not among the top-three near-term injury-rate levers.)*

### Top two success measures
1. **7210 Serious-Injury Rate (SIR, serious-injury claims per 100 person-years).** Best single outcome measure: it is exposure-normalised (so it is not distorted by the ~33% workforce growth), it targets the high-cost/high-severity end that the falls and struck-by priorities address, and it already trends cleanly in the dashboard (0.87 -> 0.58), giving a credible baseline and target.
2. **Long-recovery sprain/strain share (% of sprain/strain claims that become long-recovery).** Best leading/durational measure: it captures whether the ergonomics + early-intervention priority is working, it is the metric currently *deteriorating* (29%->35%), and it is the direct upstream driver of the LTD-heavy cost mix and days-lost. Moving it bends the cost curve, not just the count.

*(Supporting/secondary KPIs the candidate may add: claim cost per person-year, fall-from-elevation claim rate, and RTW-within-26-weeks rate.)*

## Assumptions & Disclaimers
- **Severity Index** is an analyst-defined ratio (cost share / frequency share) used to rank hazards; it is a relative indicator, not a WorkSafeBC-published metric.
- **Mixed time windows:** the accident/injury/occupation breakdowns are the dashboard's fixed 2021-2025 aggregate, whereas the trend, benefit-mix and health-care figures are 10-year (2016-2025). We did not attempt to force a common window because the dashboards do not expose one; comparisons across sections should keep this in mind.
- **External economic outlook** is an analytical inference drawn from the exposure (person-years) growth plus general BC-construction context; it is NOT sourced from a dashboard forecast. To be confirmed/replaced with an authoritative outlook (e.g. BC Stats / Construction sector forecasts) by the candidate.
- **Intervention ranking and success-measure selection** are the analyst's impact x feasibility judgement (per candidate direction) and should be reviewed and owned by the candidate before presentation.
- Ratable sectors only (70-76); self-insured employers and unknown-employer claims excluded; cost figures on the cost-drivers dashboard are charged to ratable sectors and exclude relief-of-cost, so they will not reconcile exactly with annual reports.
- Vintage: analysis is faithful to the 2023-vintage exam; a 2021-2025 re-run flag is available in the supporting scripts.

## AI-attribution log (Q4)
- Data extraction from three WorkSafeBC dashboards: Claude (browser automation); values verified by candidate against the dashboards.
- Severity-index computation and frequency-vs-cost analysis: computed by Claude; values in q4_construction_profile.csv for reproducibility.
- Judgement calls flagged for candidate ownership: (i) severity-index definition; (ii) intervention priority ranking; (iii) choice of the two success measures; (iv) external-economic-outlook inference. All confirmed by candidate to proceed on analyst's read, with assumptions stated above.
