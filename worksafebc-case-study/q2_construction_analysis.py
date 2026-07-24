"""
WorkSafeBC Case Study - Q2 analysis (Construction industry)
KPIs: Injury Rate (IR), Serious Injury Rate (SIR), Musculoskeletal Injury Rate (MSIR)
Plus Q2c: work-related death rate and four-category composition.

Data source: WorkSafeBC public Power BI dashboards
  - Provincial Overview (Report 3079), subsector 7210 = General Construction
  - Work-Related Deaths (Report 3546), sector 72 = Construction
  Data as of 2026-06-30. See q2_construction_data.csv for the extracted values.

NOTE ON WINDOWS (assignment is 2023-vintage; re-run flag kept):
  Q2 uses the last 10 completed years. With data-as-of 2026-06-30 the dashboard
  spans 2016-2025. Faithful to the exam we treat 2024 as the forecast target and
  train on 2016-2023 for the back-test. Set BACKTEST_TARGET_IDX to re-point.
No third-party libs required (pure Python) so it runs anywhere.
"""

# ---------------- Data (from q2_construction_data.csv) ----------------
YEARS = [2016,2017,2018,2019,2020,2021,2022,2023,2024,2025]
IR   = [4.15,3.93,4.06,3.67,3.42,3.47,3.08,3.07,3.11,2.98]
SIR  = [0.87,0.85,0.82,0.74,0.73,0.74,0.65,0.64,0.63,0.58]
MSIR = [1.11,1.06,1.16,1.03,0.96,1.00,0.87,0.88,0.85,0.84]

# Work-related deaths, Construction sector 72, 2015-2024
D_YEARS = [2015,2016,2017,2018,2019,2020,2021,2022,2023,2024]
DEATH_RATE = [1.70,1.69,2.60,1.70,1.61,1.51,1.31,2.26,1.57,1.01]  # per 10,000 workers
DEATH_TOT  = [30,30,51,34,34,31,29,54,39,24]
MVI        = [2,3,5,3,2,0,4,9,3,3]
OTHER_INJ  = [15,9,12,9,9,12,8,13,12,13]
ASBESTOS   = [9,18,32,19,19,15,15,26,18,5]
OTHER_DIS  = [3,0,2,3,4,2,2,6,6,3]

BACKTEST_TARGET_IDX = 8   # 2024 (train on 0..7 = 2016-2023)

# ---------------- Helpers ----------------
def mean(a): return sum(a)/len(a)

def stats(a):
    m = mean(a); v = sum((x-m)**2 for x in a)/len(a); sd = v**0.5
    return dict(mean=m, sd=sd, cv_pct=sd/m*100, min=min(a), max=max(a))

def ols(y):
    n=len(y); x=list(range(n)); mx=mean(x); my=mean(y)
    sxy=sum((x[i]-mx)*(y[i]-my) for i in range(n))
    sxx=sum((x[i]-mx)**2 for i in range(n))
    b=sxy/sxx; a=my-b*mx
    ssr=sum((y[i]-(a+b*x[i]))**2 for i in range(n))
    sst=sum((y[i]-my)**2 for i in range(n))
    r2=1-ssr/sst
    seb=((ssr/(n-2))/sxx)**0.5 if n>2 else float('nan')
    t=b/seb if seb else float('nan')
    return dict(slope=b, intercept=a, r2=r2, t=t, seb=seb)

def pearson(a,b):
    n=len(a); ma=mean(a); mb=mean(b)
    num=sum((a[i]-ma)*(b[i]-mb) for i in range(n))
    da=sum((a[i]-ma)**2 for i in range(n))**0.5
    db=sum((b[i]-mb)**2 for i in range(n))**0.5
    return num/(da*db)

def backtest(y, target_idx):
    """Fit OLS on y[0:target_idx], predict target_idx, compare to actual."""
    fit=ols(y[:target_idx])           # train on years before target
    pred=fit['intercept']+fit['slope']*target_idx
    actual=y[target_idx]
    return dict(pred=pred, actual=actual, abs_err=pred-actual,
                pct_err=(pred-actual)/actual*100)

# ---------------- Q2a: trends + interrelationships ----------------
if __name__ == '__main__':
    print('=== Q2a: 10-year trends (2016-2025) ===')
    for name,arr in [('IR',IR),('SIR',SIR),('MSIR',MSIR)]:
        s=stats(arr); t=ols(arr)
        print(f'{name}: mean={s["mean"]:.2f} cv={s["cv_pct"]:.1f}% '
              f'slope/yr={t["slope"]:+.3f} R2={t["r2"]:.2f} t={t["t"]:.1f} '
              f'total change 2016->2025={(arr[-1]/arr[0]-1)*100:+.1f}%')
    print('Correlations (Pearson):')
    print(f'  IR~SIR  = {pearson(IR,SIR):.3f}')
    print(f'  IR~MSIR = {pearson(IR,MSIR):.3f}')
    print(f'  SIR~MSIR= {pearson(SIR,MSIR):.3f}')
    print('MSIR share of IR (%):', [round(MSIR[i]/IR[i]*100,1) for i in range(len(IR))])

    # ---------------- Q2b: forecast 2024 + back-test ----------------
    print('\n=== Q2b: back-test (train 2016-2023, predict 2024) ===')
    for name,arr in [('IR',IR),('SIR',SIR),('MSIR',MSIR)]:
        bt=backtest(arr, BACKTEST_TARGET_IDX)
        print(f'{name}: pred={bt["pred"]:.3f} actual={bt["actual"]:.2f} '
              f'err={bt["abs_err"]:+.3f} ({bt["pct_err"]:+.1f}%)')
    print('Methodology: simple OLS linear trend on the annual rate series. '
          'A single 2024 point is a linear extrapolation; the 7-month coding lag '
          'means recent-year SI/MSI counts (hence SIR/MSIR) are understated when '
          'first published, biasing a naive forecast upward vs the eventual value.')

    # ---------------- Q2c: work-related deaths ----------------
    print('\n=== Q2c: Construction work-related death rate (2015-2024) ===')
    s=stats(DEATH_RATE); t=ols(DEATH_RATE)
    print(f'rate/10k: mean={s["mean"]:.2f} min={s["min"]} max={s["max"]} '
          f'slope/yr={t["slope"]:+.3f} R2={t["r2"]:.2f}')
    cats={'MVI':MVI,'Other injury':OTHER_INJ,'Asbestos':ASBESTOS,'Other disease':OTHER_DIS}
    tot={k:sum(v) for k,v in cats.items()}
    grand=sum(tot.values())
    print('10-yr category totals and share of deaths:')
    for k in cats: print(f'  {k:14s}: {tot[k]:3d}  ({tot[k]/grand*100:.1f}%)')
    disease=tot['Asbestos']+tot['Other disease']
    traum=tot['MVI']+tot['Other injury']
    print(f'  Occupational disease (Asbestos+Other) = {disease} ({disease/grand*100:.1f}%)')
    print(f'  Traumatic (MVI+Other injury)          = {traum} ({traum/grand*100:.1f}%)')
