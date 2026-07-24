# Question 3 — Findings (Roofing CUs within General Construction, Subsector 7210)

**Data source:** WorkSafeBC public Power BI "Provincial Overview (past 10 years)" (Report 3079),
Injury Rate tab + Injury Management tab. Data as of 2026-06-30. Raw extracts in
`q3_roofing_data.csv` and `q3_high_duration_data.csv`; reproducible calculations in
`q3_roofing_analysis.py`.

**Entities:** 721051 Steep Slope Roofing · 721036 Low Slope Roofing · 7210 General
Construction (subsector total). "Rest-of-7210" = subsector total minus Steep Slope,
derived from serious-injury claim counts and person-years (validated: derived Steep SIR
reproduces the published series).

**Window note (disclaimer):** "last 5 completed years" is treated as **2019–2023** to stay
faithful to what appears to be a 2023-vintage assignment. The analysis script exposes a
one-line `WIN` constant so the whole thing can be re-run on 2021–2025.

---

## Q3a — 10-year SIR trend: Steep Slope vs rest of 7210
- Steep Slope mean SIR **2.30** (SD 0.44, CV **19.2%**, range 1.60–3.21).
- Rest-of-7210 mean SIR **0.71** (SD 0.09, CV **12.9%**, range 0.57–0.85).
- Steep Slope runs at roughly **3.2× the serious-injury rate** of the rest of the sector and
  is markedly more volatile year to year. Both are trending down over the decade.

## Q3b — two statistical methods beyond descriptive
**(1) OLS linear regression of SIR on year**
- Steep Slope: slope **−0.115/yr** (−1.15/decade), t = −3.22, 95% CI [−0.198, −0.033]
  (excludes 0 → significant), but R² = 0.56 → a lot of unexplained year-to-year scatter.
- Rest-of-7210: slope **−0.031/yr**, t = −13.06, R² = 0.955 → a very tight, steady decline.

**(2) Poisson rate confidence intervals (Byar approximation) on Steep Slope SI counts**
- Steep Slope carries only **33–58 serious-injury claims/yr**, so the yearly 95% CIs are wide
  and heavily overlap (e.g. 2016: 2.64 [1.95, 3.50]; 2023: 1.93 [1.36, 2.66]).
- **Interpretation impact:** the two methods agree that the *downward trend is real*, but the
  Poisson CIs warn that any single-year jump for Steep Slope is largely small-sample noise.
  Prevention decisions should lean on the multi-year trend, not one year's number.

## Q3c — which 20% SIR reduction helps 7210 most (pooled 2019–2023)
| Scenario | New 7210 SIR | Absolute drop | Relative drop | SI claims avoided (5 yr) |
|---|---|---|---|---|
| Baseline 7210 | 0.697 | – | – | – |
| Reduce **Steep Slope** SIR 20% | 0.6935 | −0.0035 | **−0.50%** | ~40 |
| Reduce **Low Slope** SIR 20% | 0.6943 | −0.0027 | −0.39% | ~31 |

- **Steep Slope has the greater impact** — it has both the higher own-rate (pooled 2.18 vs 0.95)
  and more serious-injury claims (199 vs 157 over the window).
- **Honest caveat:** each roofing CU is <3% of the subsector's serious-injury claims, so neither
  move shifts the sector-wide SIR dramatically. The lever is real but small at the 7210 level;
  it is much larger *within roofing itself*.

## Q3d — Low Slope: % serious-injury vs % high-duration claims (10 yrs)
- Pearson **r = 0.44** (R² ≈ 0.20), t ≈ 1.39 → **weak, positive, NOT statistically significant** at n = 10.
- "% high-duration" uses the dashboard's built-in *% High Duration Claims* series (Injury Management
  tab); "% serious injury" from the Injury Rate tab.
- **Read:** for Low Slope Roofing, a higher share of serious-injury claims only weakly coincides with
  a higher share of long-duration claims — they are **not interchangeable** severity signals, so
  duration and severity should be tracked separately.

---

## Judgment calls flagged for the candidate to own
1. **Rest-of-7210 by subtraction.** I defined "all other CUs in 7210" as subsector-total minus
   Steep Slope (rather than summing every other CU individually). It is exact for rates because it
   works from claim counts and person-years, and it avoids re-extracting ~50 CUs. Confirm you are
   comfortable presenting it this way.
2. **Window = 2019–2023.** Chosen for assignment vintage; trivially switchable to 2021–2025.
3. **Q3b technique pairing.** Regression (trend/interpretability) + Poisson CIs (correct for small
   counts). Both included per your instruction.
4. **Q3d "high-duration" definition.** Used the dashboard's ready-made metric rather than building a
   custom RTW threshold (per your steer to use my judgement). RTW buckets are in the CSV if you'd
   prefer a custom cut (e.g. % still off at 26+ weeks).

## AI-attribution log (Q3)
- **Data extraction:** AI (Claude) navigated the WorkSafeBC public Power BI dashboard and transcribed
  the Steep Slope (721051), Low Slope (721036), and 7210 tables via the "Show as a table" feature.
- **Calculations:** AI wrote/ran `q3_roofing_analysis.py` (descriptive stats, OLS regression,
  Byar Poisson CIs, impact decomposition, Pearson correlation). Figures should be spot-checked by the
  candidate before submission.
- **Narrative:** AI drafted this findings summary; interpretation and framing to be reviewed and
  adopted (or edited) by the candidate, who owns the final submission.
