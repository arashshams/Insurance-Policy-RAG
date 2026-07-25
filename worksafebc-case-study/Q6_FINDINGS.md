# Q6 - Multiple Choice Questions (10 x 1 mark)

Ten short data-literacy / analytics MCQs. Answers below are the candidate's confirmed selections;
reasoning is included so the choices can be defended.

| # | Question (summary) | Answer | Why |
|---|--------------------|--------|-----|
| 1 | A p-value of 0.03 (alpha = 0.05) means... | Statistically significant - reject the null hypothesis | 0.03 < 0.05 falls in the rejection region. (It is NOT 'a 3% chance the null is true'.) |
| 2 | What does `df[df['age'] > 30]` return in pandas? | All rows where age > 30 | Boolean-mask row filter; returns the subset of rows (all columns) meeting the condition. |
| 3 | What does `np.array([1, 2, 3]) * 2` return? | [2, 4, 6] | Element-wise scalar multiply (broadcasting): each element x 2 -> [2, 4, 6]. (Not list repetition; that would be a Python list, not a numpy array.) |
| 4 | What is a confounder? | A variable that affects BOTH the independent and dependent variables, distorting the relationship | Defining property of confounding. |
| 5 | A model with high variance is... | Overfitting | Fits training noise too closely; generalizes poorly. |
| 6 | Lowering logistic threshold 0.5 -> 0.2 | Recall increases, precision decreases | More positives flagged -> more true positives (higher recall) but more false positives (lower precision). |
| 7 | Which is NOT a quality or efficiency measure? | Number of clients served | A volume/output count, not quality or efficiency. |
| 8 | Employer with the highest injury risk | Employer C (23.1%) | Highest rate among the listed options. |
| 9 | Purpose of a train/test split | To estimate performance on unseen data | Held-out test set gives an unbiased generalization estimate. |
| 10 | A database index is most effective when... | The indexed column(s) contain a wide range of distinct values (high cardinality) | High selectivity lets the index narrow results efficiently; low-cardinality columns give little benefit. |

## Confirmed answer key
1: Significant / reject null | 2: Rows where age > 30 | 3: [2, 4, 6] | 4: Affects both IV and DV | 5: Overfitting |6: Recall up, precision down | 7: Number of clients served | 8: Employer C (23.1%) | 9: Estimate performance on unseen data | 10: Wide range of distinct values

## Assumptions & Disclaimers
- For Q7, Q8, and Q10 the exact wording of the provided answer options matters; these were answered from the captured
  question set and confirmed by the candidate. Q1-Q6 and Q9 are standard, unambiguous results.
- Q8 assumes the option set lists Employer C at 23.1% as the maximum; if the live options differ, re-check the highest value.

## AI attribution
Reasoning for each MCQ was drafted with AI assistance (Claude) and reviewed/confirmed by the candidate before recording.
