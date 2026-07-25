# WorkSafeBC Case Study (Version F) - Progress Handoff

Working scratch/draft for the Senior Analytics Specialist take-home. This file lets us resume if the chat/tab is closed.

## The assignment
- WorkSafeBC take-home case study, **Version F**, Senior Analytics Specialist. 48-hour timed.
- Role-play: Senior Analytics Specialist preparing analysis for a new VP in Prevention who briefs the Board within a week.
- Board wants: BC injury rates, driving factors, prevention strategies, with **particular interest in Construction** (recent media on serious injuries/fatalities).
- Deliver 'as a report to the Head of Prevention Services'.
- Final deliverables (done by the candidate, not us): a single PowerPoint (candidate's name as filename) + a supporting Excel workbook to SharePoint; email the PPT to the administrator. Test files deleted after upload.
- AI tools permitted **with attribution**.

## How we are working
- We act as an analytical collaborator and **flag every judgment call** so the candidate can own/defend the submission.
- All calculations done **outside** the dashboards (JS/Python), then written up.
- Per question we produce: `Qn_FINDINGS.md` + a `qn_*.csv` (and .py where useful), each with an AI-attribution note.
- **Governing rule (whole assignment):** wherever we make an assumption - because data was missing OR instructions were unclear - we state it explicitly in an **Assumptions & Disclaimers** section.
- Time windows (user-confirmed): 'last 5 completed years' = **2019-2023** (faithful to the 2023-vintage exam); 'last 10 years' = 2016-2025 (KPIs). Keep a possible 2021-2025 re-run 'in mind'.
- Q1 selection is by **contribution to the provincial rate**, not injury rate alone.

## Delivery / where things live
- Repo: `arashshams/Insurance-Policy-RAG`, branch **`scratch/worksafebc-case-study`**, folder **`worksafebc-case-study/`**. Kept separate from the RAG work.
- Prefer reproducible scripts + CSV over binary xlsx (web editor can't create binaries). Data exports are part of the submission.

## Status (marks)
- **Q1 (15) - DONE**
- **Q2 (20) - DONE** (incl. 'how to improve the forecast' addition)
- **Q3 (35) - DONE**
- **Q4 (20) - DONE** (7210 profile + prioritised interventions + success measures)
- **Q5 (10) - DONE** (mental disorder claims: frequency vs cost, decision rule, psych-only vs combined)
- **Q6 (10) - REMAINING** - ten 1-mark multiple-choice questions. We will walk through the reasoning for each for the candidate to confirm; do NOT auto-fill.
- **Running total: 100 / 110.** Passing = 88/110 (80%).

## Files committed so far
- Q1_FINDINGS.md, q1_subsector_contribution.py, q1_subsector_data.csv
- Q2_FINDINGS.md, q2_construction_analysis.py, q2_construction_data.csv
- Q3_FINDINGS.md, q3_roofing_analysis.py, q3_roofing_data.csv, q3_high_duration_data.csv
- Q4_FINDINGS.md, q4_construction_profile.csv
- Q5_FINDINGS.md, q5_mental_disorder_data.csv
- PROGRESS_HANDOFF.md (this file)

## Key Q5 results (for quick reference)
- Province-wide. Psychological-injury-only allowed claims: 1,736 (2021) -> 2,607 (2025), +50%; reported +48%; allow rate fell 54% -> 45%.
- Combined (physical + accepted psychological) allowed: 913 -> 1,119 (2025), +23%.
- Cost paid 2025: psych-only $439.9M; combined $547.1M; total mental disorder ~ $987M. Psych-only cost +144% since 2016.
- Decision rule: rank by trajectory on BOTH axes (allowed-volume growth x cost); psych-only = volume driver now also a cost driver (top priority); combined = cost-severity driver (fewer but far more expensive -> early screening + RTW).
- Disclaimer: frequency counts (Report 3841, allowed-in-year) and cost counts (Report 3559, paid-in-year) use different bases and are not directly divided; 7210-only is below the >25 privacy threshold so Q5 is province-wide.

## Data sources (Power BI dashboards, all public)
- Provincial Overview (Report 3079) - injury rates, CU profile, industry claims analysis (counts & costs), 2016-2025.
- Industry Claim Cost Drivers (Report 3559) - cost by benefit type / claims characteristics / health care; excludes relief-of-cost.
- Work-Related Deaths (Report 3546) - 2004-2024; caution trending low counts.
- Mental Disorder Claims (Report 3841) - reported/allowed/eligibility, 2021-2025.
- Filter tip: Subsector 7210 = 'General Construction'; the filter resets to All on each tab/dashboard, so re-apply per tab.

## Next step
- **Q6 (10):** work through the ten MCQs one by one with reasoning; candidate confirms answers (do not auto-fill).
- Keep committing artifacts to the scratch branch; keep the Assumptions & Disclaimers convention.
