"""Best-effort free daily S&P500 scan; no synthetic market data."""
import io, json, time
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import requests
import yfinance as yf

BASE=Path('data'); BASE.mkdir(exist_ok=True)
URL='https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
NOW=datetime.now(timezone.utc).isoformat(timespec='seconds')

def save(name,payload):
    (BASE/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

def calc(frame,ticker):
    if isinstance(frame.columns,pd.MultiIndex):
        if ticker in frame.columns.get_level_values(1): frame=frame.xs(ticker,axis=1,level=1)
        elif ticker in frame.columns.get_level_values(0): frame=frame.xs(ticker,axis=1,level=0)
        else: return None
    close=pd.to_numeric(frame['Close'],errors='coerce').dropna()
    volume=pd.to_numeric(frame['Volume'],errors='coerce').dropna()
    if len(close)<205: return None
    last=close.iloc[-20:]; ma20=float(last.mean()); sigma=float(last.std(ddof=0))
    lower=ma20-2*sigma; price=float(close.iloc[-1]); prev=float(close.iloc[-2])
    if price<=0 or lower<=0: return None
    ma50=float(close.iloc[-50:].mean()); ma200=float(close.iloc[-200:].mean())
    ma20_prev=float(close.iloc[-21:-1].mean()); ma50_prev=float(close.iloc[-51:-1].mean()); ma200_prev=float(close.iloc[-201:-1].mean())
    entry={'ticker':ticker.replace('-','.'),'close':round(price,3),'date':str(close.index[-1].date())}
    breach=100*(price/lower-1)
    bb={**entry,'lower':round(lower,3),'breach_pct':round(breach,2)} if breach<=-3 else None
    # Previous close near or below MA; latest close above MA with positive day = tentative support bounce.
    bounces=[]
    for period,ma,old_ma in [(20,ma20,ma20_prev),(50,ma50,ma50_prev),(200,ma200,ma200_prev)]:
        if prev<=old_ma*1.015 and prev>=old_ma*.97 and price>ma and price>prev:
            bounces.append({**entry,'ma':period,'ma_value':round(ma,3),'day_change_pct':round((price/prev-1)*100,2),'distance_pct':round((price/ma-1)*100,2)})
    latest_volume=int(volume.iloc[-1]) if len(volume) and volume.index[-1]==close.index[-1] else 0
    vol={**entry,'volume':latest_volume,'volume_1w':int(volume.iloc[-5:].sum()) if len(volume)>=5 else None,'volume_1m':int(volume.iloc[-21:].sum()) if len(volume)>=21 else None} if latest_volume>0 else None
    upper=ma20+2*sigma
    bb_pct=(price-lower)/(upper-lower)*100 if upper>lower else None
    high_52=float(close.iloc[-252:].max())
    drawdown=(price/high_52-1)*100
    running_max=close.iloc[-252:].cummax()
    mdd=float((close.iloc[-252:]/running_max-1).min()*100)
    change_pct=(price/prev-1)*100
    dist200=(price/ma200-1)*100
    score=50
    score+=15 if price>ma200 else -15
    score+=10 if ma50>ma200 else -10
    score+=10 if change_pct>0 else -5
    score+=10 if 0<=bb_pct<=70 else (-10 if bb_pct>100 else 5)
    score+=10 if -8<=drawdown<=-2 else (0 if drawdown<0 else -5)
    score+=5 if abs(dist200)<15 else (-10 if dist200>35 else 0)
    score=max(0,min(100,score))
    grade='A' if score>=80 else 'B' if score>=65 else 'C' if score>=50 else 'D'
    if bb_pct is not None and (bb_pct>100 or dist200>35): opinion='WATCH'
    elif score>=70 and price>ma200 and -15<=drawdown<=-3: opinion='관심'
    elif price<ma200 and change_pct<0: opinion='주의'
    else: opinion='WATCH'
    report={**entry,'score':score,'grade':grade,'opinion':opinion,
        'bb_percent_b':round(bb_pct,2) if bb_pct is not None else None,
        'ma20':round(ma20,3),'ma50':round(ma50,3),'ma200':round(ma200,3),
        'distance_200_pct':round(dist200,2),'drawdown_52w_pct':round(drawdown,2),
        'mdd_52w_pct':round(mdd,2),'daily_change_pct':round(change_pct,2),
        'bb_lower':round(lower,3),'bb_upper':round(upper,3)}
    return bb,bounces,vol,report

def main():
    try:
        r=requests.get(URL,headers={'User-Agent':'Mozilla/5.0 (personal stock screener)'},timeout=30); r.raise_for_status()
        table=pd.read_html(io.StringIO(r.text),attrs={'id':'constituents'})[0]
        symbols=sorted(set(table['Symbol'].astype(str).str.replace('.','-',regex=False)))
        if len(symbols)<450: raise RuntimeError('S&P500 constituent list too short')
        breaches=[]; bounces=[]; volumes=[]; reports={}; scanned=set()
        for i in range(0,len(symbols),25):
            batch=symbols[i:i+25]
            try:
                df=yf.download(batch,period='18mo',interval='1d',auto_adjust=True,progress=False,threads=False,timeout=30)
                for symbol in batch:
                    try:
                        result=calc(df,symbol)
                        if result is None: continue
                        scanned.add(symbol); bb,ma,vol,report=result
                        reports[report["ticker"]]=report
                        if bb: breaches.append(bb)
                        bounces.extend(ma)
                        if vol: volumes.append(vol)
                    except Exception as e: print('Symbol failed:',symbol,str(e)[:120])
            except Exception as e: print('Batch failed:',i,str(e)[:150])
            time.sleep(1)
        if len(scanned)<int(len(symbols)*.9): raise RuntimeError(f'Insufficient data coverage: {len(scanned)}/{len(symbols)}')
        common={'status':'ok','updated_at_utc':NOW,'universe':'S&P 500','universe_count':len(symbols),'scanned_count':len(scanned),'source':'Yahoo Finance via unofficial yfinance; data may be delayed or unavailable','price_basis':'adjusted daily close'}
        breaches.sort(key=lambda x:x['breach_pct'])
        bounces.sort(key=lambda x:(-x['day_change_pct'],abs(x['distance_pct'])))
        save('bollinger_top5.json',{**common,'threshold_pct':-3,'window':20,'std_multiplier':2,'total_matches':len(breaches),'results':breaches[:5]})
        volumes.sort(key=lambda x:-x['volume'])
        save('volume_top50.json',{**common,'as_of_date':volumes[0]['date'] if volumes else None,'ranking':'daily share volume, not realtime','results':sorted({v['ticker']:v for period in ('volume','volume_1w','volume_1m') for v in sorted(volumes,key=lambda x:-x[period])[:50]}.values(),key=lambda x:-x['volume'])})
        save('ma_bounce_top5.json',{**common,'rule':'previous close within -3% to +1.5% of previous MA, latest close above latest MA and up on day','periods':[20,50,200],'total_matches':len(bounces),'results':bounces[:5]})
        save('quant_reports.json',{**common,'method':'Rule-based quantitative narrative, not generative AI','results':reports})
        print('Scanned:',len(scanned),'BB matches:',len(breaches),'MA matches:',len(bounces))
    except Exception as e:
        print('US scan failed, preserving previous successful JSON:',str(e))
        raise
if __name__=='__main__': main()
