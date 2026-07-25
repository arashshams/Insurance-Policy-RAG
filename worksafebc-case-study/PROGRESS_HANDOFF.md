# WorkSafeBC Case Study (Version F) - Progress Handoff

Working scratch/draft for the Senior Analytics Specialist take-home. STATUS: all six questions complete (110/110).

## The assignment
- WorkSafeBC take-home case study, **Version F**, Senior Analytics Specialist. 48-hour timed.
- Role-play: Senior Analytics Specialist preparing analysis for a new VP in Prevention who briefs the Board within a week.
- Board wants: BC injury rates, driving factors, prevention strategies, with **particular interest in Construction** (recent media on serious injuries/fatalities).
- Deliver 'as a report to the Head of Prevention Services'.
- Final deliverables (done by the candidate, not us): a single PowerPoint (candidate's name as filename) + a supporting Excel workbook to SharePoint; email the PPT to the administrator. Test files deleted after upload.
- AI tools permitted **with attribution**.

## How we worked
- Acted as an analytical collaborator and **flagged every judgment call** so the candidate can own/defend the submission.
- All calculations done **outside** the dashboards (JS/Python), then written up.
- Per question: `Qn_FINDINGS.md` + a `qn_*.csv` (and .py where useful), each with an AI-attribution note.
- **Governing rule (whole assignment):** wherever we made an assumption - missing data OR unclear instructions - we stated it in an **Assumptions & Disclaimers** section.
- Time windows (user-confirmed): 'last 5 completed years' = **2019-2023**; 'last 10 years' = 2016-2025 (KPIs). Possible 2021-2025 re-run kept 'in mind'.
- Q1 selection is by **contribution to the provincial rate**, not injury rate alone.

## Delivery / where things live
- Repo: `arashshams/Insurance-Policy-RAG`, branch **`scratch/worksafebc-case-study`**, folder **`worksafebc-case-study/`**. Kept separate from the RAG work.
- Reproducible scripts + CSV over binary xlsx (web editor can't create binaries). Data exports are part of the submission.

## Status (marks) - COMPLETE
- **Q1 (15) - DONE**
- **Q2 (20) - DONE** (incl. 'how to improve the forecast')
- **Q3 (35) - DONE**
- **Q4 (20) - DONE** (7210 profile + prioritised interventions + success measures)
- **Q5 (10) - DONE** (mental disorder claims: frequency vs cost, decision rule, psych-only vs combined)
- **Q6 (10) - DONE** (ten MCQs, reasoning + confirmed answer key)
- **Total: 110 / 110.** Passing = 88/110 (80%).

## Files committed
- Q1_FINDINGS.md, q1_subsector_contribution.py, q1_subsector_data.csv
- Q2_FINDINGS.md, q2_construction_analysis.py, q2_construction_data.csv
- Q3_FINDINGS.md, q3_roofing_analysis.py, q3_roofing_data.csv, q3_high_duration_data.csv
- Q4_FINDINGS.md, q4_construction_profile.csv
- Q5_FINDINGS.md, q5_mental_disorder_data.csv
- Q6_FINDINGS.md
- PROGRESS_HANDOFF.md (this file)

## Q6 confirmed answer key (quick reference)
1: Significant / reject null | 2: Rows where age > 30 | 3: 4 | 4: Affects both IV and DV | 5: Overfitting |
6: Recall up, precision down | 7: Number of clients served | 8: Employer C (23.1%) | 9: Estimate performance on unseen data | 10: Wide range of distinct values (high cardinality)

## Data sources (Power BI dashboards, all public)
- Provincial Overview (Report 3079) - injury rates, CU profile, industry claims analysis, 2016-2025.
- Industry Claim Cost Drivers (Report 3559) - cost by benefit type / claims characteristics / health care; excludes relief-of-cost.
- Work-Related Deaths (Report 3546) - 2004-2024.
- Mental Disorder Claims (Report 3841) - reported/allowed/eligibility, 2021-2025.
- Filter tip: Subsector 7210 = 'General Construction'; the filter resets to All per tab/dashboard - re-apply each time.

## Remaining (candidate's own actions - we cannot do these)
- Transcribe the findings into the provided PowerPoint template + supporting Excel workbook (candidate's-name filename).
- Upload to SharePoint, email the PPT to the administrator, then delete the local test files.
