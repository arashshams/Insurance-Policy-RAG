# WorkSafeBC Case Study (Version F) - Presenter's Guide / Speaker Notes

How to use this: this is your desk copy for delivering the work live. For each question
it gives what was asked, which WorkSafeBC resource the numbers came from, the method and
WHY it was chosen, the headline numbers, and the questions a panel is likely to press on
plus how to answer them. Read the "Opening" and "If challenged" sections before you go in.
All numbers trace to the committed findings; if asked for a figure not here, say you will
confirm from the dashboard rather than guessing.

---

## Opening (say this up front, ~60 seconds)

- Framing: "I'm presenting as the Senior Analytics Specialist supporting the new VP of
  Prevention. The goal is what BC's injury picture looks like, what drives it, and where
  prevention effort pays off - with a focus on Construction, as the Board asked."
- Data source: everything comes from WorkSafeBC's own public Power BI dashboards
  (Provincial Overview / Report 3079, Industry Claim Cost Drivers / 3559, Work-Related
  Deaths / 3546, Mental Disorder Claims / 3841). Figures were extracted via the dashboard
  "Show as a table" feature, then analysed outside the tool.
- Data vintage (SAY THIS - it pre-empts the most likely challenge): the assignment is
  framed around 2023, so "last 5 years" = 2019-2023 and "last 10 years" = 2016-2025
  (deaths 2015-2024). The live dashboards now run to 2025; every script has a one-line
  switch to re-run on 2021-2025, so the method is reproducible on the newest data.
- AI attribution (required by the assignment): "I used AI assistance for data extraction,
  the Python calculations, and drafting; I reviewed and own every judgment call and
  figure." State this once, plainly - it is a requirement, not a weakness.

---

## Question 1 - Which subsectors to target to get the province below 2.0

- What was asked: identify the top-3 subsectors to target so a 10% cut in their injury
  rates brings BC's provincial rate (2.08 as of 2023) below 2.0 by 2024; selection must
  be by CONTRIBUTION to the provincial rate, not injury rate alone; use the last 5
  completed years. Plus discuss other factors (employer size, claim types).
- Resource used: Provincial Overview (Report 3079), Injury Rate tab, all 24 ratable
  subsectors (sectors 70-76).
- Method + justification: contribution = each subsector's share of provincial time-loss
  claims x the official 2.08 rate, so contributions sum to the provincial rate. This is
  the right lens because it answers "who drives the provincial number," which is NOT the
  same as who has the highest rate. Chosen over ranking by injury rate precisely because
  the question demands contribution.
- Headline numbers: Top-3 = 7660 Health Care & Social Services (21.1% of claims), 7210
  General Construction (11.4%), 7610 Tourism & Hospitality (9.3%); combined 41.8%.
  A 10% cut across the three -> 2.08 x (1 - 0.418 x 0.10) = 1.995, just under 2.0. The
  exact cut needed to hit 2.0 is 9.4%, so 10% works with almost no margin.
- Part (b) factors: employer size (interventions must reach the size bands that generate
  claims), claim-type mix (Health Care is MSI-heavy, Construction serious-injury-heavy -
  a uniform 10% isn't equally feasible), 1% projected employment growth inflating the
  person-year denominator, and the thin 1.995 margin.
- If challenged:
  - "Why is Tourism in the top-3 when its rate is low (1.50)?" Because contribution is
    about volume x rate; Tourism is large, so it drives the provincial number despite a
    below-average rate. That is the whole point of the contribution lens.
  - "Do your subsector numbers reconcile to the province total?" Be honest: summing 24
    individually-filtered subsectors runs ~10-13% higher than the dashboard's province
    rollup (likely records the province nets out once but are double-counted when each
    subsector is filtered separately). I anchored shares to the OFFICIAL 2.08 and
    disclosed the gap rather than hiding it; the implied pooled rate (2.04) is within 2%.
  - "Is the intervention math realistic?" It is a linear/proportional first-order
    estimate; part (b) is exactly where I flag why real-world realisation is harder.

---

## Question 2 - Construction KPIs, forecasting, and work-related deaths

- What was asked: 10-year trends and interrelationships of the Construction KPIs; a 2024
  forecast with a back-test and how to improve it; and work-related deaths in Construction
  by the four categories.
- Resource used: Provincial Overview (3079) subsector 7210 for KPIs; Work-Related Deaths
  (Report 3546) sector 72 for deaths.
- Method + justification: simple OLS linear trend per KPI series, chosen for transparency
  and defensibility on a short 10-point series (a complex model would over-fit and be hard
  to defend to a Board). Back-test = train on 2016-2023, predict 2024, compare to actual.
- Headline numbers: IR 4.15 -> 2.98 (-28.2%), SIR 0.87 -> 0.58 (-33.3%), MSIR 1.11 ->
  0.84 (-24.3%); the three move together (Pearson 0.93-0.97). Back-test under-predicts
  slightly (IR pred 2.87 vs actual 3.11, -7.9%) because the decline flattened. Deaths
  (sector 72, 353 over 10 yrs): Asbestos 49.9%, Other injury 31.7%, MVI 9.6%, Other
  disease 8.8%; occupational disease 58.6% vs traumatic 41.3%; rate mean 1.70/10k.
- How to improve the forecast (this is explicitly graded - have it ready): correct for
  the 7-month SI/MSI coding lag that understates recent years; use quarterly data; try a
  dampened/non-linear trend or exponential smoothing; incorporate employment/exposure
  growth; report prediction intervals, not a single point.
- If challenged:
  - "Why linear, not something fancier?" With 10 annual points, a transparent linear
    trend is the honest choice; I show its weakness in the back-test and say how to
    improve it rather than over-claiming.
  - "Why analyse deaths at sector level, not subsector 7210?" Deaths are rare; sector 72
    gives more stable annual counts. That is a deliberate small-numbers choice.
  - "Asbestos is half of deaths - current or legacy?" It is largely long-latency legacy
    exposure; that is why occupational-disease control is strategic but slow, and I treat
    it as secondary to the traumatic-injury levers.

---

## Question 3 - Roofing CUs within General Construction (7210)

- What was asked: (a) 10-yr serious-injury-rate (SIR) trend for Steep Slope roofing vs
  the rest of 7210; (b) two statistical methods beyond descriptive; (c) whether a 20% SIR
  cut in Steep vs Low Slope helps 7210 more; (d) for Low Slope, the relationship between
  % serious-injury and % high-duration claims.
- Resource used: Provincial Overview (3079), Injury Rate tab + Injury Management tab;
  CUs 721051 Steep Slope, 721036 Low Slope, and 7210 total.

### Q3a
- Method: descriptive trend + variability (SD, CV). "Rest-of-7210" = subsector total
  minus Steep Slope, derived from claim counts and person-years (exact for rates; avoids
  re-extracting ~50 CUs).
- Numbers: Steep mean SIR 2.30 (CV 19.2%) vs rest 0.71 (CV 12.9%) - ~3.2x and far more
  volatile; both declining.
- If challenged ("is subtraction valid?"): yes for rates, because it works from counts
  and person-years, not from averaging rates. Confirm you are comfortable presenting it.

### Q3b
- Method + justification: (1) OLS regression of SIR on year for the trend and its
  significance; (2) Byar-approximation Poisson confidence intervals because Steep Slope
  has only 33-58 serious-injury claims a year - small counts need count-appropriate
  intervals. The pairing is deliberate: trend + correct uncertainty.
- Numbers: Steep slope -0.115/yr, t=-3.22, 95% CI excludes 0 (significant) but R2=0.56
  (noisy); rest -0.031/yr, R2=0.955 (tight). Poisson CIs for Steep are wide and overlap
  year to year.
- Takeaway to say: the downward trend is real, but any single-year spike for Steep Slope
  is mostly small-sample noise - base prevention decisions on the multi-year trend.

### Q3c
- Method: impact decomposition pooled over 2019-2023 - apply a 20% SIR cut to each CU and
  measure the effect on the 7210 SIR and claims avoided.
- Numbers: Steep Slope wins (~40 SI claims avoided over 5 yrs vs ~31 for Low Slope);
  Steep has both the higher own-rate (2.18 vs 0.95) and more claims (199 vs 157).
- Honest caveat to volunteer: each roofing CU is <3% of 7210's serious-injury claims, so
  neither move shifts the sector-wide SIR much - the lever is real but small at 7210
  level, larger within roofing itself.

### Q3d
- Method: Pearson correlation over 10 years; % high-duration uses the dashboard's built-in
  "% High Duration Claims" series (Injury Management tab).
- Numbers: r = 0.44, R2 ~ 0.20, t ~ 1.39 at n=10 - weak, positive, NOT significant.
- Takeaway: severity share and long-duration share are not interchangeable signals; track
  duration and severity separately.
- If challenged ("why the dashboard metric, not a custom threshold?"): I used the
  ready-made metric for comparability; the RTW buckets are in the CSV if a custom cut
  (e.g. still off at 26+ weeks) is preferred.

---

## Question 4 - General Construction (7210) profile and interventions

- What was asked: (a) an industry profile of 7210; (b) prioritized interventions and the
  success measures to track them.
- Resource used: Provincial Overview (3079) CU Profile + Industry Claims Analysis, and
  Industry Claim Cost Drivers (Report 3559) for cost/benefit/nature/source breakdowns.

### Q4a
- Method + justification: compare each hazard's share of COST against its share of
  FREQUENCY. I define a "severity index" = cost share / frequency share (>1 = cost-heavy
  relative to how often it happens). SAY CLEARLY this is an analyst-defined ranking ratio,
  not a WorkSafeBC-published metric.
- Numbers: Falls from Elevation are the driver - 28% of cost vs 15.7% of frequency
  (index 1.78); fractures 29.6% cost / 11.1% count (index 2.7); floors/walkways/ground
  dominate the source; ages 25-54 = 70% of cost; benefit mix LTD 35.2% / Health Care
  28.4% / STD 24.7%. Worsening signal: long-recovery sprains rose 29% -> 35% of sprains.
- If challenged ("where's the economic outlook?"): the dashboards carry no macro forecast,
  so I framed that as an explicit analytical inference from exposure/person-year growth -
  labelled as inference, not data.

### Q4b
- Method: rank interventions by impact x feasibility (impact = share of cost/serious
  injury addressable; feasibility = known, deployable controls).
- Recommendations: P1 Falls-from-elevation program (28% of cost, high feasibility);
  P2 ergonomics / manual-materials-handling for sprains & strains (high volume + the
  worsening long-recovery trend); P3 struck-by and machinery controls. Secondary:
  occupational-disease/asbestos (strategic, long latency).
- Two success measures: (1) 7210 Serious-Injury Rate - best single OUTCOME measure;
  (2) long-recovery sprain/strain share - best LEADING indicator. One outcome + one
  leading indicator is deliberate.
- If challenged ("these are judgment calls"): yes - the ranking and measure choice are my
  analyst judgment, tied directly to the cost/frequency evidence in 4a.

---

## Question 5 - Mental disorder (psychological injury) claims: frequency vs cost

- What was asked: compare frequency vs cost of allowed mental disorder claims, state the
  decision rule for reading the two together, and compare psychological-only vs combined
  physical-with-psychological claims.
- Resource used: Mental Disorder Claims (Report 3841) for frequency; Industry Claim Cost
  Drivers (Report 3559) for cost. Province-wide.
- Method + justification: a two-axis triage rule - rank a category by its trajectory on
  BOTH volume (allowed-claim growth) and cost (size/growth); a category rising on both is
  a priority; high on one axis only = "cost-severity driver" or "volume driver." SAY this
  is an analyst-defined framework, not a WorkSafeBC metric.
- Headline numbers: psych-only reported +48% (5,442 -> 8,053), allowed +50%, allow-rate
  FELL 54% -> 45%; psych-only cost +144% since 2016 ($180M -> $440M). Combined: fewer,
  slower-growing claims but higher TOTAL cost ($547M in 2025, 55% of spend) - i.e. far
  more expensive per claim. ~$987M total mental-disorder spend in 2025.
- Read to deliver: psych-only = a volume driver that is now also a cost driver ->
  upstream psychological-health/exposure prevention + faster, consistent adjudication
  (the falling allow-rate is itself a signal). Combined = cost-severity driver -> early
  intervention and active return-to-work to stop the high-cost tail.
- If challenged:
  - "Are frequency and cost on the same basis?" No - and this matters. Frequency counts
    are claims reported/allowed in the year; cost counts are claims paid in the year (a
    larger active population). I compare cost TOTALS directly but deliberately AVOID
    per-claim ratios across the two dashboards because the denominators differ.
  - "Why province-wide, not Construction?" Mental-disorder claims filtered to 7210 fall
    below the >25-claims privacy threshold, so a reliable Construction-only split isn't
    disclosable. That is a data-availability constraint, not a choice.

---

## Question 6 - Ten technical MCQs

- What was asked: ten short data-literacy / analytics multiple-choice questions.
- No dashboard - these are knowledge questions. Confirmed answer key (i)-(x):
  (i) p=0.03 at alpha 0.05 -> significant, reject the null.
  (ii) df[df['age'] > 30] -> all rows where age > 30 (boolean-mask filter).
  (iii) np.array([1,2,3]) * 2 -> [2, 4, 6] (element-wise scalar multiply).
  (iv) A confounder affects BOTH the independent and dependent variables.
  (v) High variance -> overfitting.
  (vi) Lowering the logistic threshold 0.5 -> 0.2: recall up, precision down.
  (vii) NOT a quality/efficiency measure: number of clients served (a volume count).
  (viii) Highest injury risk = Employer C at a RATE of 23.1% (a calculated rate, not a
    raw count - say "rate" explicitly if asked).
  (ix) Purpose of a train/test split: estimate performance on unseen data.
  (x) A database index is most effective with high-cardinality columns (a wide range of
    distinct values).
- If challenged on (viii): stress it is the RATE (23.1%), highest among the listed
  options, not just the largest count.

---

## General "if challenged" / defense playbook

- "How current is this?" 2023-vintage framing by design; reproducible on 2021-2025 via a
  one-line switch in each script.
- "Did AI do this for you?" AI assisted with extraction, calculation, and drafting; I
  reviewed and own every number and judgment call. (Required attribution - state calmly.)
- "Can you reproduce a figure?" Yes - the Python scripts (Q1, Q2, Q3) embed the raw data
  and the calculations; Q4/Q5 numbers were derived manually from the cited dashboards and
  are recorded in the findings.
- "What are you least sure about?" Be candid: the Q1 subsector-to-province rollup gap
  (disclosed, shares anchored to 2.08), and the analyst-defined metrics (Q4 severity
  index, Q5 triage rule) which are interpretive framings, not official measures.

---

## Presenter checklist (last 5 minutes before you walk in)

- Know your three headline stories cold: Q1 (contribution != rate; 41.8% -> 1.995),
  Q2 (all KPIs down ~25-33%, deaths half asbestos), Q5 (psych-only volume vs combined
  cost).
- Have the data-vintage line and the AI-attribution line ready to say once, early.
- Flag analyst-defined metrics as such before anyone asks (severity index, triage rule).
- For any number you don't have, offer to confirm from the dashboard - never guess.
