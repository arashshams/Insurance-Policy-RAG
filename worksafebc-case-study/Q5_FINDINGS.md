# Q5 - Mental Disorder (Psychological Injury) Claims: Frequency vs Cost

**Question (Version F, 10 marks):** Compare the frequency vs the cost of *allowed* mental disorder claims,
state the decision rule used to interpret the two together, and compare psychological-injury-**only** claims
against **combined** physical-with-accepted-psychological-injury claims.

**Framing:** Prepared as an input to the Head of Prevention Services / VP Prevention briefing to the Board.
Scope is province-wide (ratable sectors 70-76), because mental disorder claims are a cross-industry issue;
a Construction (7210) read is added as a sub-note where the data supports it.

## Data sources
- **Frequency:** Mental Disorder Claims dashboard (Report 3841, data as of 2026-07-06) - Trend tab, eligibility-decision table. Counts are claims *reported* and *allowed in the year*.
- **Cost:** Industry Claim Cost Drivers dashboard (Report 3559, data as of 2026-06-30) - Claim Costs by Benefit Types ($), All Benefit. `$` are amounts *paid in the year*; the accompanying claim count is *claims receiving any payment in the year*.
- Window: 5-year view (2021-2025) for frequency; cost trend available 2016-2025. Consistent with the case's 'last 5 completed years' framing.

## 1. Frequency of allowed mental disorder claims (province-wide)

Psychological Injury **Only** claims (reported vs allowed, allow rate):

| Year | Reported | Allowed | Disallowed | Allow rate |
|------|---------:|--------:|-----------:|-----------:|
| 2021 | 5,442 | 1,736 | 1,462 | 54% |
| 2022 | 5,882 | 1,973 | 1,511 | 57% |
| 2023 | 6,757 | 2,187 | 2,013 | 52% |
| 2024 | 7,243 | 2,414 | 2,578 | 48% |
| 2025 | 8,053 | 2,607 | 3,127 | 45% |

Combined (Physical **with accepted** Psychological Injury) - allowed claims: 913 (2021) -> 986 -> 988 -> 1,128 -> 1,119 (2025).

**Read:** Reported psychological-only claims rose +48% (5,442 -> 8,053) and allowed claims +50% (1,736 -> 2,607)
over five years, while the **allow rate fell from 54% to 45%** - i.e. demand is rising faster than acceptance,
and disallowed volume more than doubled. Combined claims are far fewer and grew more slowly (+23%).
In 2025 there were ~3,726 allowed mental disorder claims in total; combined claims are only ~30% of that.

## 2. Cost of mental disorder claims (province-wide, paid in year)

| Year | Psych-only $ paid | Combined $ paid |
|------|------------------:|----------------:|
| 2016 | $180.2M | $303.3M |
| 2021 | $271.2M | $414.7M |
| 2023 | $379.9M | $502.4M |
| 2025 | $439.9M | $547.1M |

Growth: psych-only cost **+144% since 2016** (+62% since 2021); combined cost +80% since 2016 (+32% since 2021).
Total mental disorder claim cost paid in 2025 is roughly **$987M** (psych-only $439.9M + combined $547.1M).

## 3. Frequency vs cost together - the decision rule

**Decision rule used:** *Rank/triage a claim category by the product of its trajectory on BOTH axes -
how fast the volume of allowed claims is growing AND how large / fast-growing its cost is - and treat a
category as a priority when it is rising on both. Where a category is high on one axis only, classify it as
either a 'cost-severity' driver (high cost, lower volume) or a 'volume' driver (high/growing volume, lower unit cost)
and match the prevention response accordingly.*

Applying it:
- **Psychological-injury-only** = a **volume driver that is now also a cost driver**: fastest-growing volume (+50% allowed)
  AND fastest-growing cost (+144% since 2016). This is the category to prioritise for prevention (it is accelerating on both axes).
- **Combined physical+psychological** = a **cost-severity driver**: fewer, slower-growing claims but the highest total cost
  ($547M in 2025, 55% of mental disorder spend). These are expensive, long-running claims - the priority here is early
  intervention / return-to-work to stop physical injuries developing a secondary psychological component.

## 4. Psychological-only vs combined - the key contrast

- **Volume:** psych-only dominates (2,607 allowed vs 1,119 in 2025) and is growing faster.
- **Total cost:** combined is *larger* ($547.1M vs $439.9M) despite ~half the allowed volume -> **combined claims are much more
  expensive per claim** (they carry an accepted physical injury plus psychological sequelae, driving long-duration/LTD cost).
- **Implication:** the two need different strategies. Psych-only -> upstream psychological-health/exposure prevention and
  faster, more consistent adjudication (the falling allow rate is itself a signal). Combined -> early psychological screening
  on serious physical-injury claims and active RTW to prevent escalation to the high-cost tail.

## Assumptions & Disclaimers
- **Two different count bases.** Frequency counts (Report 3841) are claims *reported/allowed in the year*; the cost dashboard's
  (Report 3559) claim counts are *claims receiving any payment in the year* (a much larger active population - e.g. 72,400
  paid combined claims in 2025 vs 1,119 newly allowed). Cost totals are compared directly; per-claim ratios across the two
  dashboards are **not** and are avoided.
- **Province-wide, not Construction-specific.** Mental disorder claims filtered to Subsector 7210 fall below the dashboards'
  privacy threshold (>25 allowed claims/year), so a reliable Construction-only split is not available; the analysis is done
  province-wide. This is an assumption made because the industry-level data was not disclosable.
- **Cost basis.** Cost dashboard values are charged to ratable sectors only and **exclude relief-of-cost**, so they will not
  reconcile exactly with annual-report figures.
- **Decision rule is analyst-defined.** The two-axis (volume x cost trajectory) rule and the 'volume driver vs cost-severity
  driver' labels are our chosen interpretive framework, not a WorkSafeBC-published metric.
- **Window.** 5-year frequency window (2021-2025) matches the case's 'last 5 completed years'; cost trend uses the fuller
  2016-2025 series where available. Some intermediate years were not individually captured (marked blank in the CSV).
- **2023-vintage exam note.** Consistent with the rest of this submission, the underlying assessment is 2023-vintage; the live
  dashboards now extend to 2025, so figures are the current values for the same report objects.

## AI attribution
Data extracted from the WorkSafeBC public Power BI dashboards and derived statistics (growth rates, shares, per-claim proxies)
computed outside the dashboards with AI assistance (Claude). All interpretation, the decision rule, and the assumptions above
were reviewed by the candidate. See q5_mental_disorder_data.csv for the underlying figures.
