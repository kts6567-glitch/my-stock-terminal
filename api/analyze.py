"""Free best-effort, on-demand daily US equity analysis. No paid API key.
Data source: Yahoo Finance unofficial chart endpoint. Not suitable for trading execution.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from datetime import datetime, timezone
import json, math, re, statistics, time, csv, io


def rolling_mean(v, n):
    return [None if i+1<n else sum(v[i-n+1:i+1])/n for i in range(len(v))]

def ema(v, n):
    alpha=2/(n+1); out=[]; last=None
    for x in v:
        last=x if last is None else alpha*x+(1-alpha)*last
        out.append(last)
    return out

def rsi(v,n=14):
    out=[None]*len(v)
    if len(v)<n+2:return out
    gains=[max(v[i]-v[i-1],0) for i in range(1,len(v))]
    losses=[max(v[i-1]-v[i],0) for i in range(1,len(v))]
    ag=sum(gains[:n])/n;al=sum(losses[:n])/n
    for i in range(n,len(gains)):
        ag=(ag*(n-1)+gains[i])/n;al=(al*(n-1)+losses[i])/n
        out[i+1]=100 if al==0 else 100-100/(1+ag/al)
    out[n]=100 if al==0 else 100-100/(1+ag/al)
    return out

KR_NAMES = {'005930.KS':'삼성전자','000660.KS':'SK하이닉스','035420.KS':'NAVER','035720.KS':'카카오','005380.KS':'현대차','000270.KS':'기아','051910.KS':'LG화학','006400.KS':'삼성SDI','373220.KS':'LG에너지솔루션','207940.KS':'삼성바이오로직스','068270.KS':'셀트리온','105560.KS':'KB금융','055550.KS':'신한지주','086790.KS':'하나금융지주','012450.KS':'한화에어로스페이스','042700.KS':'한미반도체','247540.KQ':'에코프로비엠','086520.KQ':'에코프로','196170.KQ':'알테오젠','091990.KQ':'셀트리온헬스케어'}

def analyze(ticker):
    error=None;item={};source='Yahoo Finance 비공식 일봉'
    for domain in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
        try:
            url=f'https://{domain}/v8/finance/chart/{quote(ticker)}?range=3y&interval=1d&events=history'
            req=Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
            with urlopen(req,timeout=9) as response: raw=json.load(response)
            chart=raw['chart']; item=chart['result'][0]; quote_data=item['indicators']['quote'][0]
            timestamps=item['timestamp']; rows=[]
            for i,ts in enumerate(timestamps):
                try:
                    c=quote_data['close'][i]; o=quote_data['open'][i]; h=quote_data['high'][i]; l=quote_data['low'][i]
                    if any(x is None or not math.isfinite(float(x)) for x in (c,o,h,l)):continue
                    rows.append({'date':datetime.fromtimestamp(ts,timezone.utc).strftime('%Y-%m-%d'),'open':float(o),'high':float(h),'low':float(l),'close':float(c),'volume':int(quote_data['volume'][i] or 0)})
                except (IndexError,ValueError,TypeError):continue
            if len(rows)<205:raise ValueError('200일선 분석에 필요한 거래일 데이터가 부족합니다.')
            break
        except Exception as e:
            error=str(e);rows=[]
    if not rows and not ticker.endswith(('.KS','.KQ')):
        # Secondary public delayed daily source for US tickers, not an official exchange feed.
        try:
            stooq_symbol=ticker.replace('.','-').lower()+'.us'
            req=Request('https://stooq.com/q/d/l/?s='+quote(stooq_symbol)+'&i=d',headers={'User-Agent':'Mozilla/5.0'})
            with urlopen(req,timeout=10) as response: body=response.read(1500000).decode('utf-8-sig')
            entries=list(csv.DictReader(io.StringIO(body)))
            rows=[]
            for x in entries[-850:]:
                try:
                    vals=[float(x[k]) for k in ('Open','High','Low','Close')]
                    if all(math.isfinite(v) and v>0 for v in vals):
                        rows.append({'date':x['Date'],'open':vals[0],'high':vals[1],'low':vals[2],'close':vals[3],'volume':int(float(x.get('Volume') or 0))})
                except (KeyError,ValueError,TypeError):continue
            if len(rows)<205:rows=[]
            else:source='Stooq 비공식 일봉 (Yahoo 조회 실패 시 대체)'
        except Exception as e:error=str(error)+' / Stooq: '+str(e)
    if not rows:raise RuntimeError('무료 시세 데이터 조회 실패: '+str(error)[:180])
    c=[x['close'] for x in rows]; n=len(c); ma20=rolling_mean(c,20);ma50=rolling_mean(c,50);ma200=rolling_mean(c,200)
    rsi14=rsi(c); e12=ema(c,12);e26=ema(c,26); macd=[a-b for a,b in zip(e12,e26)]; signal=ema(macd,9);hist=[a-b for a,b in zip(macd,signal)]
    bands=[]
    for i in range(n):
        if i<19:bands.append((None,None));continue
        chunk=c[i-19:i+1]; mean=ma20[i]; sd=statistics.pstdev(chunk)
        bands.append((mean-2*sd,mean+2*sd))
    price=c[-1];prev=c[-2]; lower,upper=bands[-1];bpercent=(price-lower)/(upper-lower)*100 if upper>lower else None
    dist=(price/ma200[-1]-1)*100; high52=max(c[-252:]);drawdown=(price/high52-1)*100
    running=c[-252:];peak=running[0];mdd=0
    for x in running:
        peak=max(peak,x);mdd=min(mdd,(x/peak-1)*100)
    change=(price/prev-1)*100
    score=50+(15 if price>ma200[-1] else -15)+(10 if ma50[-1]>ma200[-1] else -10)+(10 if change>0 else -5)
    score+=(10 if bpercent is not None and 0<=bpercent<=70 else -10 if bpercent is not None and bpercent>100 else 5)
    score+=(10 if -8<=drawdown<=-2 else 0 if drawdown<0 else -5)
    score+=(5 if abs(dist)<15 else -10 if dist>35 else 0)
    score=max(0,min(100,score));grade='A' if score>=80 else 'B' if score>=65 else 'C' if score>=50 else 'D'
    opinion='관망' if bpercent is not None and (bpercent>100 or dist>35) else ('관심' if score>=70 and price>ma200[-1] and -15<=drawdown<=-3 else '주의' if price<ma200[-1] and change<0 else '관망')
    vol20=sum(x['volume'] for x in rows[-21:-1])/20
    volratio=rows[-1]['volume']/vol20 if vol20 else None
    # Signals are descriptive and not verified trading recommendations.
    signals=[]
    for k,p in [('20',ma20),('50',ma50),('200',ma200)]:
        if p[-2] is not None and c[-2]<=p[-2]*1.015 and c[-2]>=p[-2]*.97 and price>p[-1] and price>prev:
            signals.append(k+'일선 지지 후 반등 후보')
    if rsi14[-1] is not None and rsi14[-1]<30:signals.append('RSI 과매도')
    if rsi14[-1] is not None and rsi14[-1]>70:signals.append('RSI 과열')
    if macd[-2]<signal[-2] and macd[-1]>=signal[-1]:signals.append('MACD 상향 교차')
    if macd[-2]>signal[-2] and macd[-1]<=signal[-1]:signals.append('MACD 하향 교차')
    if bpercent is not None and bpercent<0:signals.append('볼린저밴드 하단 이탈')
    if bpercent is not None and bpercent>100:signals.append('볼린저밴드 상단 돌파')
    meta=item.get('meta',{}); company=KR_NAMES.get(ticker) or meta.get('longName') or meta.get('shortName') or ticker
    def rnd(x):return None if x is None else round(x,3)
    series=[]
    for i,x in enumerate(rows):
        series.append({**x,'ma20':rnd(ma20[i]),'ma50':rnd(ma50[i]),'ma200':rnd(ma200[i]),'rsi':rnd(rsi14[i]),'macd':rnd(macd[i]),'macdSignal':rnd(signal[i]),'macdHist':rnd(hist[i])})
    return {'status':'ok','ticker':ticker,'company':company,'date':rows[-1]['date'],'fetched_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'data_source':source+' · 지연/차단 가능','market':'KR' if ticker.endswith(('.KS','.KQ')) else 'US','currency':'KRW' if ticker.endswith(('.KS','.KQ')) else 'USD','price_basis':'일봉 비수정 종가','close':rnd(price),'daily_change_pct':rnd(change),'volume':rows[-1]['volume'],'volume_ratio':rnd(volratio),'rsi':rnd(rsi14[-1]),'macd':rnd(macd[-1]),'macd_signal':rnd(signal[-1]),'ma20':rnd(ma20[-1]),'ma50':rnd(ma50[-1]),'ma200':rnd(ma200[-1]),'bb_lower':rnd(lower),'bb_upper':rnd(upper),'bb_percent_b':rnd(bpercent),'distance_200_pct':rnd(dist),'drawdown_52w_pct':rnd(drawdown),'mdd_52w_pct':rnd(mdd),'score':score,'grade':grade,'opinion':opinion,'signals':signals,'series':series[-760:]}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query);ticker=q.get('ticker',[''])[0].upper().strip()
        market=q.get('market',['US'])[0].upper()
        if market not in ('US','KR'):
            self.reply(400,{'status':'error','error':'market은 US 또는 KR만 가능합니다.'});return
        if market=='KR':
            if re.fullmatch(r'\d{6}',ticker):ticker=ticker+'.KS'
            if not re.fullmatch(r'\d{6}\.(KS|KQ)',ticker):
                self.reply(400,{'status':'error','error':'한국 종목은 6자리 코드 또는 005930.KS / 247540.KQ 형식으로 입력하세요.'});return
        elif not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,11}',ticker):
            self.reply(400,{'status':'error','error':'미국 종목코드를 입력하세요 (예: ASTS, MU, BRK-B).'});return
        try:self.reply(200,analyze(ticker))
        except Exception as e:self.reply(503,{'status':'error','error':str(e)[:240]})
    def reply(self,code,obj):
        data=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','public, max-age=60, s-maxage=300');self.send_header('Access-Control-Allow-Origin','*');self.end_headers();self.wfile.write(data)
