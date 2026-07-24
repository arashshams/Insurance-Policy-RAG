# PROGRESS HANDOFF - WorkSafeBC Case Study (Senior Analytics Specialist)

> Purpose: session-continuity note. If this browser tab/chat is lost, read this to resume exactly where we left off. Last updated after committing the Q2b forecast-improvement edit.

## 1. Assignment context (Version F - current)
- Role: Senior Analytics Specialist preparing analysis for a new VP in Prevention who briefs the Board of Directors within a week. BOD wants: BC injury rates, driving factors, prevention strategies, with **particular focus on the Construction industry** (recent media on serious injuries/fatalities).
- Framing: deliver 'as though it was a report to the Head of Prevention Services'. Timed 48-hour take-home.
- Deliverables (candidate does these, NOT Claude): (1) a SINGLE PowerPoint (blank template provided), filename = candidate name; (2) a supporting Excel workbook with ALL working data/calculations, same filename, saved to SharePoint; email the PPT to the administrator. AI tools permitted WITH attribution. Test files must be permanently deleted after upload.
- **This is a confidential recruitment assessment testing the CANDIDATE.** Claude acts as an analytical collaborator and FLAGS every judgment call so the candidate can own/defend the submission. No black-box answers. For Q6 MCQs, Claude will walk through reasoning for each and let the candidate confirm - NOT auto-fill.

### Version F changes vs the earlier version (already reconciled)
- **NEW Question 6 (10 marks): ten 1-mark MCQs** (analysis/knowledge, not dashboard extraction). Total is now **110 marks**; passing **88/110 (80%)**. Marks: Q1=15, Q2=20, Q3=35, Q4=20, Q5=10, Q6=10.
- 'Information Provided' names 7 Power BI solutions: Provincial overview (past 10 years); Provincial overview (last year & year-to-date); Industry claims analysis STD/LTD/Fatal; Industry claim cost drivers; Work-related deaths; Industry risks (prevention data); Mental disorder claims.
- Q2 hint sharpened: ties the 7-month coding lag to the 'last year and year to date' dashboard for forecasting. Q2b added the sub-ask 'How can the forecast be improved?' (now answered).
- Q1-Q5 otherwise substantively identical.

## 2. Questions (marks)
- **Q1 (15):** (a,10) top 3 subsectors by CONTRIBUTION to provincial rate (NOT injury rate alone), last 5 completed years, 10% reduction to bring province <2.0 by 2024; contribution table + show 10% effect. (b,5) other factors (employer size, claim types).
- **Q2 (20):** IR/SIR/MSIR. (a,7) 10-yr trends + interrelationships, quantified. (b,8) forecast 2024, justify method, back-test predicting 2024 from <=2023 + error + 'how to improve forecast' + Python in appendix; HINT 7-month coding lag. (c,5) work-related deaths over 10 yrs across four categories.
- **Q3 (35):** (a,7) 10-yr SIR Steep Slope (721051) vs rest-of-7210. (b,8) statistical method beyond descriptive [did BOTH]. (c,10) 20% SIR reduction Steep vs Low (721036) impact decomposition, last 5 yrs. (d,10) Low Slope %SI vs %high-duration over 10 yrs.
- **Q4 (20):** (a,10) 7210 profile (claim drivers, CUs, accidents, claim types, occupations, cost drivers, days lost, industry risks/inspection/regulation/accident-investigation, top benefit type, top healthcare cost drivers by program type, external economic outlook). (b,10) prioritized interventions by impact+feasibility; top two success measures.
- **Q5 (10):** frequency vs cost of allowed mental disorder claims; state decision rule; psychological-only vs combined physical+psychological.
- **Q6 (10, NEW):** ten MCQs (p-value, pandas filtering, numpy, confounder, overfitting, logistic threshold, quality/efficiency measure, highest-injury-risk employer table, train/test split rationale, DB index usefulness).

## 3. Progress status
- **DONE: Q1 (15), Q2 (20), Q3 (35) = 70/110 marks covered.**
- **REMAINING: Q4 (20), Q5 (10), Q6 (10).** Next session starts at Q4.

## 4. Delivery / GitHub
- Branch: **scratch/worksafebc-case-study** on repo **arashshams/Insurance-Policy-RAG**, folder **worksafebc-case-study/**. Kept SEPARATE from the RAG work. Prefer reproducible scripts/CSV (web editor cannot create binary xlsx). Data exports included in submission.
- Files committed so far:
  - Q1_FINDINGS.md, q1_subsector_contribution.py, q1_subsector_data.csv
  - Q2_FINDINGS.md (incl. new 'How can the forecast be improved?'), q2_construction_analysis.py, q2_construction_data.csv
  - Q3_FINDINGS.md, q3_roofing_analysis.py, q3_roofing_data.csv, q3_high_duration_data.csv
- Every question keeps a running AI-attribution log; every judgment call is flagged.

## 5. Scope decisions & data windows (candidate-confirmed)
- 'Last 5 completed years' = **2019-2023** (kept faithful to the 2023-vintage exam). Add a vintage disclaimer in the deck. Idea kept 'in mind': optionally re-run on a 2021-2025 window (a re-run flag/window constant is exposed in scripts).
- 'Last 10 years': KPIs 2016-2025; deaths 2015-2024 (complete years only).
- Q1 selection MUST be by contribution to provincial rate, not injury rate alone.
- Calculations done OUTSIDE the dashboard (Python).
- Data notes: ratable sectors only (70-76); self-insured excluded; Person Years not shown for Fishing; deaths dashboard cautions against trending low counts.

## 6. Key data & results captured
### Q1 - by contribution to provincial rate (2019-2023). See Q1_FINDINGS.md + q1 files.
### Q2 (subsector 7210 KPIs, 2016->2025)
- IR: 4.15,3.93,4.06,3.67,3.42,3.47,3.08,3.07,3.11,2.98
- SIR: 0.87,0.85,0.82,0.74,0.73,0.74,0.65,0.64,0.63,0.58
- MSIR: 1.11,1.06,1.16,1.03,0.96,1.00,0.87,0.88,0.85,0.84
- Person-years: 159704,178629,181755,191842,185729,198718,215773,224977,216419,213005
- Q2a: IR slope -0.139/yr R2 0.92 (-28.2%); SIR -0.032 R2 0.96 (-33.3%); MSIR -0.035 R2 0.85 (-24.3%). Pearson IR~SIR 0.97, IR~MSIR 0.96, SIR~MSIR 0.93. MSIR ~28-32% of IR.
- Q2b back-test (train 2016-2023 -> 2024): IR pred 2.87 vs 3.11 (-7.9%); SIR 0.60 vs 0.63 (-4.5%); MSIR 0.84 vs 0.85 (-0.9%). OLS under-predicts (decline flattened). Improvement ideas now in Q2_FINDINGS.md.
### Q2c - Construction (sector 72) work-related deaths, 2015->2024
- Rate/10k: 1.70,1.69,2.60,1.70,1.61,1.51,1.31,2.26,1.57,1.01 (mean 1.70; slope -0.06/yr R2 0.17 = no reliable trend).
- Totals: 30,30,51,34,34,31,29,54,39,24 (353 over 10 yr).
- 10-yr composition: Asbestos 176 (49.9%), Other injury 112 (31.7%), MVI 34 (9.6%), Other disease 31 (8.8%). Occupational disease 58.6% vs traumatic 41.4%.
### Q3 - roofing (721051 Steep Slope, 721036 Low Slope) vs rest-of-7210. See Q3_FINDINGS.md + q3 files.

## 7. Technical / browser notes for resuming
- **Provincial Overview** = Power BI Report 3079. Tab in this session: 1805194692. URL r-token: eyJrIjoiNWM3ZmI0OTYtNzdmYi00ZjhjLThiNWYtNTE3MjdkY2FlNjFhIiwidCI6IjA1YzVjOTYzLWM4MzktNGM5ZS1iNWMxLWI1MWIzNzk5YWMzNyJ9 . 'Data as of 2026-06-30', spans 2016-2025.
- **Work-Related Deaths** = Power BI Report 3546. Tab: 1805195975. URL r-token: eyJrIjoiMDE0MTU0YzMtYzA1Yy00ZjFlLWE3NDctMTg2Y2E1NmRmNjZjIiwidCI6IjA1YzVjOTYzLWM4MzktNGM5ZS1iNWMxLWI1MWIzNzk5YWMzNyJ9 . Spans 2004-2024. Death categories: 1:MVI, 3:Other injury, 5:Asbestos exposure, 6:Other disease.
- WorkSafeBC hub tab: 1805195955 -> worksafebc.com/en/about-us/data-insights/industry-health-safety-data (links to all 7 dashboards).
- Power BI tips: switch tabs by COORDINATE click on the visible tab label (ref clicks unreliable); read tables via JS grid reader; hover data points for exact tooltip values; multi-select slicers can toggle unintended items - verify via zoom.
- GitHub web-editor tips: create/edit file, click editor body, write content to clipboard using real newlines (String.fromCharCode(10) join - NOT literal backslash-n), Ctrl+A/Delete then Ctrl+V (first paste sometimes fails; verify + repeat), set filename LAST (watch out: a mis-click can open the global search palette - press Escape and retry), then Commit directly to scratch/worksafebc-case-study.
- Allowed domains: worksafebc.com, app.powerbi.com, powerbi.com, github.com. Google navigation is blocked.
- BOUNDARY: Claude cannot access SharePoint / the PPT template / upload final files - those are the candidate's actions.

## 8. Next step when resuming
Start **Q4 (20)**: build the 7210 comprehensive profile (using Industry claims analysis, Industry claim cost drivers, and Industry risks dashboards) then prioritized interventions + top two success measures. Then Q5 (mental disorder claims) and Q6 (MCQs - present reasoning for candidate to confirm). Continue committing artifacts to scratch/worksafebc-case-study.
