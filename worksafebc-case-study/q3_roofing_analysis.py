"""
WorkSafeBC Case Study - Question 3 analysis (roofing CUs within General Construction 7210)
==========================================================================================
Answers:
  Q3a  10-yr SIR trend: Steep Slope Roofing (721051) vs all other CUs in 7210 combined,
       with variability (SD, coefficient of variation) and year-over-year change.
  Q3b  TWO statistical methods beyond descriptive:
         (1) OLS linear regression of SIR on year (slope significance + 95% CI)
         (2) Poisson rate confidence intervals on the serious-injury counts (Byar approx)
  Q3c  20% SIR reduction: Steep Slope vs Low Slope (721036) - which helps 7210 more.
       Impact-decomposition table, pooled over the last 5 completed years (2019-2023).
  Q3d  Low Slope (721036): relationship between % serious-injury claims and
       % high-duration claims over 10 years (Pearson correlation).

Data source: WorkSafeBC public Power BI "Provincial Overview (past 10 years)",
Injury Rate tab and Injury Management tab (Report 3079). Data as of 2026-06-30.
All figures extracted via the dashboard "Show as a table" feature; see the
q3_roofing_data.csv and q3_high_duration_data.csv files for the raw extracts.

NOTE on windows: "last 5 completed years" is taken as 2019-2023 to stay faithful to a
2023-vintage assignment (see project disclaimer). Change WIN below to re-run for 2021-2025.

Requires: numpy, scipy (optional; falls back to hand-coded stats if scipy absent).
"""
import numpy as np

YEARS = [2016,2017,2018,2019,2020,2021,2022,2023,2024,2025]
WIN   = [2019,2020,2021,2022,2023]            # last 5 completed years (assignment vintage)
widx  = [YEARS.index(y) for y in WIN]

# ---- Raw extracts (Injury Rate tab) ----
steep = dict(  # 721051 Steep Slope Roofing
    sir=[2.64,3.21,2.47,1.97,2.69,2.04,2.31,1.93,2.16,1.60],
    si =[48,58,45,35,45,38,44,37,42,33],
    py =[1819,1808,1818,1780,1674,1866,1905,1921,1940,2058])
low = dict(    # 721036 Low Slope Roofing
    sir=[1.32,0.93,1.13,0.99,0.74,0.91,1.08,1.01,0.60,0.67],
    si =[39,29,38,34,24,29,35,35,22,26],
    py =[2962,3107,3364,3420,3250,3198,3231,3455,3654,3873],
    pct_si=[21,13,18,20,17,17,21,22,16,18],
    pct_hd=[28.0,18.2,19.0,21.2,23.9,23.0,23.0,26.4,23.8,31.5])  # % high-duration (Injury Mgmt tab)
tot = dict(    # 7210 General Construction (subsector total)
    sir=[0.87,0.85,0.82,0.74,0.73,0.74,0.65,0.64,0.63,0.58],
    si =[1386,1520,1494,1426,1348,1477,1396,1446,1356,1235],
    py =[159704,178629,181755,191842,185729,198718,215773,224977,216419,213005])

# Rest-of-7210 (all other CUs) = subsector total minus Steep Slope
rest_si = [tot['si'][i]-steep['si'][i] for i in range(10)]
rest_py = [tot['py'][i]-steep['py'][i] for i in range(10)]
rest_sir= [round(rest_si[i]/rest_py[i]*100,3) for i in range(10)]

def desc(a):
    a=np.array(a,float); m=a.mean(); sd=a.std(ddof=0)
    return dict(mean=round(m,3), sd=round(sd,3), cv_pct=round(sd/m*100,1),
                min=round(a.min(),2), max=round(a.max(),2))

def yoy(a):
    return [None]+[round(a[i]-a[i-1],3) for i in range(1,len(a))]

# ================= Q3a =================
print("="*70,"\nQ3a  SIR trend: Steep Slope (721051) vs rest of 7210\n","="*70)
print("Steep Slope SIR:", steep['sir'])
print("Rest-of-7210 SIR:", rest_sir)
print("Steep stats     :", desc(steep['sir']))
print("Rest  stats     :", desc(rest_sir))
print("Ratio of means  :", round(desc(steep['sir'])['mean']/desc(rest_sir)['mean'],2),"x")
print("Steep YoY change:", yoy(steep['sir']))
print("Rest  YoY change:", yoy(rest_sir))

# ================= Q3b (1) OLS regression =================
def ols(y):
    x=np.arange(len(y)); y=np.array(y,float); n=len(y)
    b,a=np.polyfit(x,y,1); yh=a+b*x; sse=((y-yh)**2).sum(); df=n-2
    seb=np.sqrt((sse/df)/((x-x.mean())**2).sum())
    t=b/seb; r2=1-sse/((y-y.mean())**2).sum()
    tcrit=2.306  # t(0.975, df=8)
    return dict(slope=round(b,4), slope_per_decade=round(b*10,3), se=round(seb,4),
                t=round(t,3), r2=round(r2,3),
                ci95=[round(b-tcrit*seb,4), round(b+tcrit*seb,4)])
print("\n"+"="*70,"\nQ3b(1)  OLS regression of SIR on year\n","="*70)
print("Steep Slope:", ols(steep['sir']))
print("Rest-of-7210:", ols(rest_sir))
print("Read: CI excluding 0 => significant trend. Low r2 + wide CI (Steep) => noisy.")

# ================= Q3b (2) Poisson rate CIs (Byar) =================
def byar(k, exposure):
    lo=k*(1-1/(9*k)-1.96/(3*np.sqrt(k)))**3
    hi=(k+1)*(1-1/(9*(k+1))+1.96/(3*np.sqrt(k+1)))**3
    return (round(lo/exposure*100,3), round(hi/exposure*100,3))
print("\n"+"="*70,"\nQ3b(2)  Poisson 95% CI on Steep Slope serious-injury rate\n","="*70)
for i,y in enumerate(YEARS):
    r=round(steep['si'][i]/steep['py'][i]*100,3)
    print(y, "rate", r, "CI", byar(steep['si'][i], steep['py'][i]))
print("Read: overlapping CIs across years => small counts (33-58/yr) make single-year")
print("swings largely statistical noise; the *trend* (Q3b-1) is the reliable signal.")

# ================= Q3c 20% reduction impact (pooled 2019-2023) =================
def pool(o):
    si=sum(o['si'][i] for i in widx); py=sum(o['py'][i] for i in widx)
    return si, py, round(si/py*100,4)
S=pool(steep); L=pool(low); T=pool(tot)
base=T[2]
def scenario(cu):
    new_si=T[0]-0.20*cu[0]; new=new_si/T[1]*100
    return dict(new_SIR=round(new,4), abs_drop=round(base-new,4),
                rel_drop_pct=round((base-new)/base*100,3), claims_avoided=round(0.20*cu[0],1))
print("\n"+"="*70,"\nQ3c  20% SIR reduction, pooled 2019-2023\n","="*70)
print("Subsector 7210 baseline SIR:", base)
print("Steep pooled (SI,PY,SIR):", S, " share of 7210 SI:", round(S[0]/T[0]*100,2),"%")
print("Low   pooled (SI,PY,SIR):", L, " share of 7210 SI:", round(L[0]/T[0]*100,2),"%")
print("Reduce STEEP 20% ->", scenario(S))
print("Reduce LOW   20% ->", scenario(L))
print("Conclusion: Steep Slope reduction has the larger impact on the 7210 SIR")
print("(higher own-rate AND more serious-injury claims). Both effects small in absolute")
print("terms because each CU is <3% of subsector serious-injury claims.")

# ================= Q3d correlation =================
def pearson(x,y):
    x=np.array(x,float); y=np.array(y,float); n=len(x)
    r=np.corrcoef(x,y)[0,1]; t=r*np.sqrt((n-2)/(1-r*r))
    return dict(r=round(r,3), r2=round(r*r,3), t=round(t,3), n=n)
print("\n"+"="*70,"\nQ3d  Low Slope: %serious-injury vs %high-duration (10 yrs)\n","="*70)
print("% Serious Injury:", low['pct_si'])
print("% High Duration :", low['pct_hd'])
print("Pearson:", pearson(low['pct_si'], low['pct_hd']))
print("Read: r~0.44 (weak, positive), t~1.39 => NOT significant at n=10. The share of")
print("serious-injury claims is only weakly associated with the share of high-duration")
print("claims for Low Slope Roofing; they are not interchangeable severity signals.")
