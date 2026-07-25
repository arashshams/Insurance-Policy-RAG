# WorkSafeBC Case Study - Question 1 (Findings & Method)

> Confidential recruitment assessment. Draft working notes prepared with AI assistance
> (see "AI attribution" at the end). All figures traceable to the WorkSafeBC public
> Power BI dashboard "Provincial Overview (past 10 years)", Injury Rate tab, extracted
> via right-click > "Show as a table". Dashboard "Data as of: 2026-06-30".

## Question restated
BC's provincial injury rate was **2.08 (as of 2023)**, the aggregate of 24 ratable
subsectors. Employment is expected to grow ~1% next year in Manufacturing,
Construction, Transportation & Warehousing, and Service; all others static.
- **(a, 10)** Identify the top 3 subsectors to target so that a 10% reduction in
  their injury rates brings the overall provincial rate below 2.0 by 2024.
  Selection **must be based on contribution to the provincial rate, not injury rate
  alone**, using the **last 5 completed years** (not a single year).
- **(b, 5)** Discuss other factors (employer size, claim types) affecting whether the
  10% reduction is realised.

## Method
- **Window:** 2019-2023 (last five completed injury years, consistent with the "2.08
  as of 2023" and "below 2.0 by 2024" framing). *See disclaimer re: 2021-2025.*
- **Injury rate definition (verified):** time-loss claims per 100 person-years.
  Province 2023 = 53,702 / 2,579,485 x 100 = 2.082 (matches published 2.08).
- **Contribution metric:** each subsector's share of total time-loss claims,
  multiplied by the official provincial rate. Contributions therefore sum to the
  provincial rate. This isolates "which subsectors drive the provincial number",
  which is *not* the same as ranking by injury rate.
- Calculations are in q1_subsector_contribution.py (regenerates q1_outputs.xlsx and
  q1_subsector_data.csv). Raw 2016-2025 extractions for all 24 subsectors are embedded
  in that script for full traceability.

## DATA-SCOPE DISCLAIMER (important, flag to reviewer)
Summing the 24 individually-filtered subsectors does **not** equal the dashboard's
province-wide "All" total: the subsector sum runs ~10.5% higher on claims and ~12.8%
higher on person-years (2023). The implied pooled rate from the subsector sum (2.04)
is nonetheless within ~2% of the official province rate (2.08), so **relative shares
are robust**. The contribution table is therefore built on claim SHARES anchored to
the official 2.08, with this rollup gap disclosed rather than hidden. Likely cause:
employers/records that WorkSafeBC's province rollup nets out or classifies once are
picked up when each subsector is filtered separately.

## Result (2019-2023, anchored to official 2.08)
**Top 3 contributors:**
1. **7660 Health Care & Social Services** - claim share ~21.1%, own injury rate ~4.40
2. **7210 General Construction** - claim share ~11.4%, own injury rate ~3.33
3. **7610 Tourism and Hospitality** - claim share ~9.3%, own injury rate ~1.50

Combined they account for **~41.8%** of provincial time-loss claims.

**Key teaching point (why contribution != rate):** Tourism makes the top 3 on sheer
size despite a *below-average* injury rate (~1.50), while high-rate but small
subsectors (e.g. Warehousing ~4.67, Forestry ~4.13) barely move the provincial number.

**Intervention math:** a 10% cut to each of the top-3 subsectors' injury rates removes
~10% of their claims, i.e. 0.10 x their combined 41.8% share of the rate.
- New provincial rate = 2.08 x (1 - 0.418 x 0.10) = **~1.995** -> just clears < 2.0.
- The reduction on the top-3 needed to hit *exactly* 2.0 is **~9.4%** -> the 10%
  target works but with almost no margin (fragile; ties into part (b)).

## Part (b) - factors affecting realisation (draft)
- **Employer size:** claims concentrate in specific size bands; a 10% rate cut is only
  achievable if interventions reach the size segments that actually generate the
  claims (large employers vs. many small ones with weaker safety infrastructure).
- **Claim-type mix:** MSI and serious-injury claims behave differently; cutting
  high-frequency low-severity claims moves the rate faster than cutting rare severe
  claims. The three targets have different mixes (Health Care is MSI-heavy;
  Construction is serious-injury-heavy), so a uniform "10%" is not equally feasible.
- **Employment growth:** 1% projected growth in Construction/Transportation/etc.
  raises person-years (the denominator) AND exposure; if claims grow with headcount,
  the rate cut must overcome that drift.
- **Thin margin:** because 1.995 barely clears 2.0, any adverse movement (a bad year
  in a fourth subsector, coding lag, growth) can push it back over 2.0.

## AI attribution (running log for this question)
- AI assistant (Claude) extracted the 24-subsector data from the dashboard, wrote the
  Python analysis, computed the contribution table and intervention math, and drafted
  these notes. All numbers are candidate-verifiable against the cited dashboard.
- Judgment calls made WITH the candidate: 5-year window = 2019-2023; contribution
  anchored to official 2.08; report the 10% result honestly incl. the thin margin.


## Assumptions & Disclaimers (Q1)

**5-year window = 2019-2023.** Chosen as the last five completed injury years, consistent with the "2.08 as of 2023" and "below 2.0 by 2024" framing. A 2021-2025 re-run is available via the WIN flag in q1_subsector_contribution.py.

**Contribution anchored to the official 2.08.** Summing the 24 individually-filtered subsectors overshoots the province rollup (~10.5% on claims, ~12.8% on person-years for 2023; implied pooled rate 2.04 vs official 2.08). The contribution table is therefore built on each subsector's SHARE of time-loss claims multiplied by the official 2.08, not on the raw subsector sum. The rollup gap is disclosed, not hidden; relative shares are robust to within ~2%.

**Injury-rate definition:** time-loss claims per 100 person-years (verified: 53,702 / 2,579,485 x 100 = 2.082, matches published 2.08).

**Selection is by contribution to the provincial rate, not injury rate alone** (per the question); this is why Tourism (7610) makes the top 3 on size despite a below-average own rate.

**Intervention math is linear/proportional:** a 10% cut to each top-3 subsector's rate is assumed to remove ~10% of its claims (new provincial rate = 2.08 x (1 - 0.418 x 0.10) = ~1.995). The ~9.4% cut needed to hit exactly 2.0 means the 10% target clears < 2.0 with almost no margin (fragile) - see part (b).

**AI attribution:** data extraction, Python analysis, contribution table and intervention math drafted with AI assistance (Claude); all figures candidate-verifiable against the cited dashboard.
