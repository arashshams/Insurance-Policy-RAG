# WorkSafeBC Case Study (Version F) - Handoff for Deliverable Build

Purpose: structured handoff so a follow-on session can build the final PowerPoint
(candidate name as filename) + supporting Excel workbook. Compiled by retracing the
real committed work product on branch scratch/worksafebc-case-study, folder
worksafebc-case-study/. Every figure below is traceable to the committed
Qn_FINDINGS.md files and the three Python scripts (raw data embedded in each script).

PROVENANCE HONESTY NOTE: The analysis was produced in an earlier session and committed
to GitHub. This handoff was compiled by re-reading those committed files, not by
re-pulling dashboards or re-running code in this session.

## Global Notes

- Reference window / data vintage: The live dashboards now extend to 2025, but the
  analysis is deliberately anchored to the 2023-vintage exam framing.
  "Last 5 completed years" = 2019-2023. "Last 10 years" = 2016-2025 for KPIs;
  2015-2024 for work-related deaths (as the death dashboard exposes them).
  Each Python script has a one-line window switch to re-run on 2021-2025.
- Recurring assumptions across questions:
  - Selection is by CONTRIBUTION to the provincial rate, not injury rate alone (Q1).
  - Ratable sectors 70-76 only; self-insured / unknown-employer claims excluded.
  - AI attribution is present per question (assignment requirement).
  - Some interpretive metrics are analyst-defined, not WorkSafeBC-published:
    the "severity index" (Q4) and the two-axis triage rule (Q5).
- Double-check before building the deck/workbook:
  1. Q1 rollup gap: summing 24 individually-filtered subsectors runs ~10-13% higher
     than the dashboard province total; findings anchor shares to the official 2.08
     and disclose the gap rather than hiding it.
  2. Q4 and Q5 derived figures were computed MANUALLY (no script) - spot-check them
     against q4_construction_profile.csv and q5_mental_disorder_data.csv.
  3. Confirm whether the exam supplied a fixed PowerPoint/Excel TEMPLATE - that
     changes how workbook formulas should be wired.
  4. Q6(viii) must be presented as the RATE 23.1%, not a raw count.
  5. No .xlsx workbook exists yet; the Q1 script references q1_outputs.xlsx but that
     file was never committed. The workbook must be built by the follow-on session/user.

## STEP 1 - Audit checklist (completeness at a glance)

All questions (Q1, Q2, Q3a-d, Q4a-b, Q5, Q6 i-x) are FULLY DRAFTED and committed.
No question is unattempted. Gaps are in deliverable packaging only: no Excel workbook
exists, and two files referenced inside scripts were never committed
(q1_outputs.xlsx, AI_ATTRIBUTION.md).

Python used: Q1, Q2, Q3 = yes (real scripts). Q4, Q5, Q6 = no (manual / MCQ).

## Question 1

- Final answer: Top-3 subsectors by contribution to the provincial rate:
  7660 Health Care & Social Services (claim share 21.1%, own IR 4.40),
  7210 General Construction (11.4%, IR 3.33),
  7610 Tourism & Hospitality (9.3%, IR 1.50). Combined = 41.8% of provincial
  time-loss claims. A 10% cut to each of their injury rates gives
  new provincial rate = 2.08 x (1 - 0.418 x 0.10) = 1.995 -> just clears < 2.0
  (the exact reduction needed to hit 2.0 is 9.4%, so the 10% target works with
  almost no margin - fragile; ties into part b).
- Reasoning / judgment calls: Selection by CONTRIBUTION (claim share x official rate),
  not injury rate alone (per the question). Contribution isolates which subsectors
  drive the provincial number; Tourism makes the top-3 on size despite a below-average
  IR, while high-rate small subsectors (Warehousing 4.67, Forestry 4.13) barely move it.
- Key numbers for slide/table: 41.8% combined share; 1.995 post-intervention rate;
  9.4% break-even reduction. Part b factors: employer size, claim-type mix
  (Health Care MSI-heavy, Construction serious-injury-heavy), 1% employment growth
  inflating the denominator, thin 1.995 margin.
- Assumptions: 5-year window = 2019-2023; contribution anchored to official 2.08;
  injury-rate = time-loss claims per 100 person-years (verified 53,702/2,579,485x100
  = 2.082); intervention math is linear/proportional. Rollup gap disclosed.
- Completeness: FULLY COMPLETE.
- Where the calc lives: q1_subsector_contribution.py (all 24 subsectors' claims +
  person-years 2016-2025 embedded) and q1_subsector_data.csv. NOTE: script references
  q1_outputs.xlsx which was NOT committed.

## Question 2

- Final answer: All three Construction (7210) KPIs declined materially over 2016-2025:
  Injury Rate 4.15 -> 2.98 (-28.2%), Serious IR 0.87 -> 0.58 (-33.3%),
  MSI Rate 1.11 -> 0.84 (-24.3%). The three move together (Pearson IR~SIR 0.97,
  IR~MSIR 0.96, SIR~MSIR 0.93). Forecast (OLS linear trend) back-test - train
  2016-2023, predict 2024: IR pred 2.87 vs actual 3.11 (-7.9%), SIR 0.60 vs 0.63
  (-4.5%), MSIR 0.84 vs 0.85 (-0.9%); model under-predicts because the decline
  flattened in 2023-2024. Q2c work-related deaths (sector 72, 2015-2024): rate mean
  1.70/10k (range 1.01 in 2024 to 2.60 in 2017); 10-yr composition of 353 deaths:
  Asbestos 176 (49.9%), Other injury 112 (31.7%), MVI 34 (9.6%), Other disease 31
  (8.8%); grouped occupational disease 58.6% vs traumatic 41.3%.
- Reasoning / judgment: Simple OLS linear trend chosen for transparency/defensibility
  on a 10-point series. Deaths analysed at sector-72 level (more stable counts than
  subsector 7210 for rare events).
- Forecast improvement (REQUIRED by the case study): correct for the 7-month SI/MSI
  coding lag; use more granular (quarterly) data; try non-linear / dampened trend or
  exponential smoothing; incorporate exposure/employment growth; widen with prediction
  intervals rather than a single point.
- Assumptions: KPI window 2016-2025; deaths 2015-2024; coding-lag caveat; death
  categories read from chart labels and sum exactly to annual totals.
- Completeness: FULLY COMPLETE (incl. required forecast-improvement discussion).
- Where the calc lives: q2_construction_analysis.py (OLS, Pearson, back-test, deaths
  composition; pure Python) + q2_construction_data.csv.

## Question 3a

- Final answer: Steep Slope Roofing (721051) mean SIR 2.30 (SD 0.44, CV 19.2%, range
  1.60-3.21) vs rest-of-7210 mean SIR 0.71 (SD 0.09, CV 12.9%, range 0.57-0.85).
  Steep Slope runs ~3.2x the serious-injury rate of the rest of the sector and is far
  more volatile; both trend down over the decade.
- Reasoning / judgment: "Rest-of-7210" defined by SUBTRACTION (subsector total minus
  Steep Slope) from SI counts and person-years - exact for rates, avoids re-extracting
  ~50 CUs.
- Key numbers: 2.30 vs 0.71; ~3.2x; CV 19.2% vs 12.9%.
- Assumptions: window per project (10-yr trend 2016-2025); subtraction method.
- Completeness: FULLY COMPLETE.
- Where the calc lives: q3_roofing_analysis.py + q3_roofing_data.csv.

## Question 3b

- Final answer: Two methods beyond descriptive. (1) OLS linear regression of SIR on
  year: Steep Slope slope -0.115/yr, t=-3.22, 95% CI [-0.198,-0.033] (excludes 0 ->
  significant) but R2=0.56 (much unexplained scatter); rest-of-7210 slope -0.031/yr,
  t=-13.06, R2=0.955 (tight steady decline). (2) Poisson rate CIs (Byar approx) on
  Steep Slope SI counts (only 33-58 claims/yr): yearly 95% CIs are wide and overlap
  (e.g. 2016: 2.64 [1.95,3.50]; 2023: 1.93 [1.36,2.66]).
- Reasoning / judgment: Regression gives trend/interpretability; Poisson CIs correctly
  handle small counts. Together: the downward trend is real, but any single-year jump
  for Steep Slope is largely small-sample noise -> base prevention decisions on the
  multi-year trend.
- Assumptions: annual rate series; Byar approximation for Poisson intervals.
- Completeness: FULLY COMPLETE.
- Where the calc lives: q3_roofing_analysis.py (uses numpy/scipy, hand-coded fallback).

## Question 3c

- Final answer: A 20% SIR reduction in Steep Slope helps 7210 MORE than the same cut
  in Low Slope. Pooled 2019-2023: baseline 7210 SIR 0.697; reduce Steep Slope 20% ->
  0.6935 (-0.50%, ~40 SI claims avoided over 5 yr); reduce Low Slope 20% -> 0.6943
  (-0.39%, ~31 claims). Steep Slope has both the higher own-rate (pooled 2.18 vs 0.95)
  and more SI claims (199 vs 157 over the window).
- Reasoning / judgment: Impact decomposition pooled over the 5-year window. Honest
  caveat: each roofing CU is <3% of the subsector's SI claims, so neither move shifts
  the 7210-wide SIR dramatically - the lever is real but small at 7210 level (larger
  within roofing itself).
- Key numbers: Steep 40 vs Low 31 claims avoided; own-rates 2.18 vs 0.95.
- Assumptions: 5-year window 2019-2023; proportional 20% reduction.
- Completeness: FULLY COMPLETE.
- Where the calc lives: q3_roofing_analysis.py + q3_roofing_data.csv.

## Question 3d

- Final answer: For Low Slope Roofing (721036), the relationship between % serious-injury
  claims and % high-duration claims over 10 years is weak, positive, and NOT
  statistically significant: Pearson r = 0.44 (R2 ~ 0.20), t ~ 1.39 at n=10.
- Reasoning / judgment: "% high-duration" uses the dashboard's built-in
  % High Duration Claims series (Injury Management tab); "% serious injury" from the
  Injury Rate tab. Read: severity share and long-duration share are not interchangeable
  signals - track duration and severity separately.
- Assumptions: dashboard's ready-made high-duration metric (not a custom RTW threshold;
  RTW buckets are in the CSV if a custom cut is preferred).
- Completeness: FULLY COMPLETE.
- Where the calc lives: q3_roofing_analysis.py + q3_high_duration_data.csv.

## Question 4a

- Final answer (7210 industry profile): Large, improving-but-still-elevated subsector;
  IR fell 4.15 -> 2.98 over 2016-2025. Frequency-vs-severity lens (2021-2025):
  Falls from Elevation are THE driver - 28.0% of cost vs 15.7% of frequency
  (severity index 1.78); MVI severity index 1.91 (small volume); Overexertion and
  Struck By are high-frequency/lower-severity. Nature: fractures 29.6% of cost /
  11.1% of count (index 2.7). Source: floors/walkways/ground surfaces dominate
  (29.4% cost, 19.5% count). Body part by count: wrist/fingers/hand 22.3%, back 17.8%.
  Ages 25-54 = 70% of cost ($815M of $1.164B SLF, 2021-2025). Benefit mix
  (2016-2025): LTD 35.2%, Health Care 28.4%, STD 24.7%, Other 11.7%. Worsening signal:
  long-recovery sprains rose from 29% to 35% of all sprains over the decade.
- Reasoning / judgment: "Severity index" = cost share / frequency share is an
  ANALYST-DEFINED ranking ratio (>1 = cost-heavy relative to frequency), not a
  WorkSafeBC metric. External economic outlook is an analytical INFERENCE (dashboards
  carry no macro forecast), framed from exposure/person-year growth.
- Key numbers: falls 28% cost / 15.7% freq; fractures index 2.7; LTD 35.2%;
  sprain long-recovery 29%->35%.
- Assumptions: mixed windows (accident/nature/source breakdowns are the dashboard's
  fixed 2021-2025 aggregate; trends are 2016-2025). Ratable sectors only.
- Completeness: FULLY COMPLETE.
- Where the calc lives: q4_construction_profile.csv. NO Q4 Python script - severity
  index and breakdowns were computed MANUALLY; figures are in Q4_FINDINGS.md.

## Question 4b

- Final answer (prioritized interventions + success measures): Ranked by impact x
  feasibility. P1 Falls-from-elevation program (highest impact/high feasibility -
  28% of cost). P2 Manual-materials-handling / ergonomics for sprains & strains
  (high volume + the worsening long-recovery share). P3 Struck-by and
  machinery/mobile-equipment controls (targeted severity). Secondary: occupational-
  disease/asbestos exposure control (strategically important, long latency).
  Top TWO success measures: (1) 7210 Serious-Injury Rate (SIR) - best single outcome
  measure; (2) Long-recovery sprain/strain share - best leading indicator.
- Reasoning / judgment: Analyst impact-x-feasibility ranking; measures chosen as one
  outcome + one leading indicator.
- Assumptions: intervention ranking and measure selection are the analyst's judgment.
- Completeness: FULLY COMPLETE.
- Where the calc lives: judgment-based; Q4_FINDINGS.md (no script).

## Question 5

- Final answer (mental disorder claims, province-wide): Psychological-injury-only:
  reported rose +48% (5,442 -> 8,053, 2021-2025), allowed +50% (1,736 -> 2,607),
  allow-rate FELL 54% -> 45%, disallowed volume more than doubled. Combined
  (physical + accepted psychological): fewer, slower-growing (allowed 913 -> 1,119,
  +23%). Cost (paid in year): psych-only $180.2M (2016) -> $439.9M (2025), +144%;
  combined $303.3M -> $547.1M, +80%. Total 2025 mental-disorder spend ~ $987M.
  Contrast: psych-only dominates VOLUME and grows faster; combined is larger in TOTAL
  COST ($547M vs $440M) despite about half the allowed volume -> combined claims are
  much more expensive per claim.
- Decision rule (analyst-defined): two-axis triage - rank a category by the product of
  its trajectory on BOTH volume (allowed-claim growth) and cost (size/growth); treat as
  priority when rising on both. High on one axis only = classify as a "cost-severity
  driver" (high cost, lower volume) or "volume driver" (high/growing volume). Applied:
  psych-only = volume driver now also a cost driver -> prioritise upstream prevention;
  combined = cost-severity driver -> early intervention + active RTW to stop the
  high-cost tail.
- Key numbers: allow-rate 54%->45%; psych-only cost +144%; combined $547M (55% of
  spend); ~$987M total 2025.
- Assumptions: TWO DIFFERENT COUNT BASES - frequency (Report 3841) = claims
  reported/allowed in year; cost (Report 3559) = claims paid in year (larger active
  population). Cost totals compared directly; per-claim ratios across the two dashboards
  are AVOIDED. Province-wide (Construction-only split suppressed by >25-claim privacy
  threshold). Cost excludes relief-of-cost.
- Completeness: FULLY COMPLETE.
- Where the calc lives: q5_mental_disorder_data.csv. NO Q5 Python script - growth rates
  computed MANUALLY; figures in Q5_FINDINGS.md.

## Question 6

Ten MCQs; reasoning in Q6_FINDINGS.md. Answers (i)-(x):
- (i) p-value 0.03 at alpha 0.05 = statistically significant, reject the null.
- (ii) df[df['age'] > 30] returns all rows where age > 30 (boolean-mask filter).
- (iii) np.array([1,2,3]) * 2 returns [2, 4, 6] (element-wise scalar multiply).
- (iv) A confounder is a variable that affects BOTH the independent and dependent
  variables.
- (v) A model with high variance is overfitting.
- (vi) Lowering the logistic threshold 0.5 -> 0.2: recall increases, precision decreases.
- (vii) NOT a quality/efficiency measure: number of clients served (a volume/output count).
- (viii) Employer with the highest injury risk = Employer C at a RATE of 23.1%
  (calculated rate, not a raw count; highest among the listed options).
- (ix) Purpose of a train/test split: estimate performance on unseen data.
- (x) A database index is most effective when the indexed column(s) contain a wide range
  of distinct values (high cardinality).
- Completeness: FULLY COMPLETE. Answer key confirmed and synced across Q6_FINDINGS.md
  and PROGRESS_HANDOFF.md.

## STEP 2 - File inventory (what actually exists vs requested structure)

Requested /data/ used a raw_/transformed_ split and one CSV per Q3 CU. That split does
NOT physically exist and was NOT invented. Actual committed data files (each is the
dashboard extract; derived results live in the scripts + findings, not separate
"transformed" CSVs):
- q1_subsector_data.csv        (Q1 raw: 24 subsectors, claims + person-years 2016-2025)
- q2_construction_data.csv     (Q2 raw: IR/SIR/MSIR + deaths + composition)
- q3_roofing_data.csv          (Q3 raw: Steep 721051, Low 721036, 7210 totals - SIR/counts)
- q3_high_duration_data.csv    (Q3d raw: % high-duration for Low Slope 721036)
- q4_construction_profile.csv  (Q4 raw: accident/nature/source/cost/benefit breakdowns)
- q5_mental_disorder_data.csv  (Q5 raw: frequency + cost by year)

Q1/Q2/Q3 "transformed" results are computed inside the scripts (and stated in findings).
Q4 and Q5 transformations were done MANUALLY (no output file) - the resulting numbers
are in Q4_FINDINGS.md and Q5_FINDINGS.md respectively (see the "Where the calc lives"
lines above). Nothing is silently lost.

Actual committed /code/ (genuinely written and run):
- q2_construction_analysis.py  (REQUIRED Q2 forecasting + back-test; also Q2a/Q2c)
- q3_roofing_analysis.py        (Q3a-d incl. Q3b OLS+Byar Poisson CIs, Q3d Pearson)
- q1_subsector_contribution.py  (Q1 contribution + intervention math)
No Q4 or Q5 script exists (manual). No incomplete/broken scripts to report.

Supporting narrative files (richer than this answers.md; keep for the build):
- Q1_FINDINGS.md, Q2_FINDINGS.md, Q3_FINDINGS.md, Q4_FINDINGS.md, Q5_FINDINGS.md,
  Q6_FINDINGS.md, PROGRESS_HANDOFF.md

Files that DO NOT EXIST (so no one hunts for them): any raw_/transformed_ CSV split,
per-CU Q3 CSVs, any Q6 data file, q1_outputs.xlsx, AI_ATTRIBUTION.md, any .xlsx
workbook, any .pptx, any zip archive.

## STEP 3 - Packaging note

A zip cannot be produced in this environment. All handoff files already live on branch
scratch/worksafebc-case-study in folder worksafebc-case-study/. Base URL for any file:
https://github.com/arashshams/Insurance-Policy-RAG/blob/scratch/worksafebc-case-study/worksafebc-case-study/<filename>

Remaining candidate-owned actions (cannot be done by an AI session): build the .pptx
(candidate name as filename) + supporting .xlsx workbook, upload to SharePoint, email
the PPT to the administrator, then delete local test files.
