# Q2 - Construction industry KPIs, forecasting, and work-related deaths (20 marks)

**Scope:** General Construction subsector (7210) for KPI trends/forecasts; Construction sector (72) for work-related deaths.
**Data:** WorkSafeBC Provincial Overview (Report 3079) and Work-Related Deaths (Report 3546) dashboards, data as of 2026-06-30.
**Windows:** Q2 uses the last 10 completed years. KPI series span 2016-2025; deaths span 2015-2024.
**Disclaimer (vintage):** The exam is 2023-vintage. We keep the analysis faithful to a 2024 forecast target (train on <=2023) and expose a re-run flag in the script for an alternate window.

---

## Q2a - 10-year trends and interrelationships

All three KPIs declined materially over the decade (rates per 100 person-years):

| KPI | 2016 | 2025 | Mean | CV | OLS slope/yr | R2 | Total change |
|-----|------|------|------|----|--------------|----|--------------|
| Injury Rate (IR)   | 4.15 | 2.98 | 3.49 | 11.9% | -0.139 | 0.92 | -28.2% |
| Serious IR (SIR)   | 0.87 | 0.58 | 0.73 | 13.0% | -0.032 | 0.96 | -33.3% |
| MSI Rate (MSIR)    | 1.11 | 0.84 | 0.98 | 11.1% | -0.035 | 0.85 | -24.3% |

**Interrelationships (Pearson):** IR~SIR = 0.97, IR~MSIR = 0.96, SIR~MSIR = 0.93 - the three rates move together very tightly, so IR is a strong lead indicator for the two severity/type-specific rates. SIR fell fastest (-33%), meaning the *mix* is improving (fewer serious claims per injury), not just the overall count. MSIR is the single largest component of IR (~28-32% of all injuries are MSI every year), so musculoskeletal prevention is where the volume is.

## Q2b - Forecasting 2024 and back-test

**Method:** simple OLS linear trend on each annual rate series (transparent, defensible for a ~10-point series; documented in the appendix script q2_construction_analysis.py).

**Back-test - train on 2016-2023, predict 2024, compare to actual:**

| KPI | Predicted 2024 | Actual 2024 | Error | % error |
|-----|----------------|-------------|-------|---------|
| IR   | 2.87 | 3.11 | -0.25 | -7.9% |
| SIR  | 0.60 | 0.63 | -0.03 | -4.5% |
| MSIR | 0.84 | 0.85 | -0.01 | -0.9% |

The linear model **under-predicts** all three because the multi-year decline flattened in 2023-2024. MSIR is the most forecastable (0.9% error); IR the least (7.9%).

**Data-quality caveat (assignment hint):** SI and MSI claims carry a ~7-month coding lag, so the most recent year's SIR/MSIR are *understated* at first publication and revise upward. A naive same-year forecast off provisional counts therefore risks over-stating the decline; treat 2024/2025 as provisional.

## Q2c - Work-related deaths in Construction (sector 72), 2015-2024

**Rate (accepted work-related deaths per 10,000 workers):** mean 1.70; range 1.01 (2024) to 2.60 (2017). The OLS slope is slightly negative (-0.06/yr) but weak (R2 = 0.17) - i.e. **no statistically reliable trend**; year-to-year moves are dominated by small-number volatility (WorkSafeBC's own note cautions against trending low counts).

**Composition by the four categories (10-year totals, 353 deaths):**

| Category | Deaths (10 yr) | Share |
|----------|----------------|-------|
| Asbestos exposure | 176 | 49.9% |
| Other injury (traumatic, non-MVI) | 112 | 31.7% |
| Motor vehicle incident (MVI) | 34 | 9.6% |
| Other occupational disease | 31 | 8.8% |

**Grouped:** Occupational disease (asbestos + other disease) = 58.6%; traumatic (MVI + other injury) = 41.4%. **Asbestos alone is the single largest cause** - mirroring the province-wide '54% occupational disease' headline. Strategic message: unlike injury *rates* (driven by MSI/traumatic events), construction *fatalities* are dominated by long-latency disease from historical asbestos exposure, which today's injury-prevention programs will not move. Prevention here is exposure-control + legacy remediation, on a different time horizon.

---

### AI-attribution log (Q2)
- Data extraction from WorkSafeBC dashboards: Claude (browser automation), values verified by candidate.
- Statistics (OLS, correlations, back-test): computed by Claude; code committed for reproducibility and candidate review.
- Judgment calls: (i) sector-72 scope for deaths (more stable counts than subsector 7210 for rare events); (ii) OLS forecast method for transparency; (iii) 2024 as back-test target faithful to exam vintage. All flagged for candidate ownership.

### Data note / reconciliation
Category counts were read from chart labels; the four categories sum exactly to the annual total in 8 of 10 years (2015 and 2020 differ by 1-2 due to label-read tolerance). Annual totals are authoritative.
