"""Best-effort intraday OHLCV via unofficial Yahoo Finance chart API.
Not exchange-certified realtime; may be delayed, rate-limited, or unavailable.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from datetime import datetime, timezone
import json, re

INTERVALS={'1m':('1m','5d'),'3m':('1m','5d'),'5m':('5m','1mo'),'15m':('15m','1mo'),'30m':('30m','1mo'),'60m':('60m','3mo'),'240m':('60m','3mo')}

def fetch(ticker, interval):
    source,period=INTERVALS[interval]
    last_error='시세 공급처 응답 없음'
    for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
        url=f'https://{host}/v8/finance/chart/{quote(ticker)}?range={period}&interval={source}&includePrePost=false'
        try:
            req=Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
            with urlopen(req,timeout=13) as response: data=json.load(response)
            result=data['chart']['result'][0]
            timestamps=result.get('timestamp') or []
            q=(result.get('indicators',{}).get('quote') or [{}])[0]
            rows=[]
            for i,ts in enumerate(timestamps):
                try:
                    o,h,l,c=(q[k][i] for k in ('open','high','low','close'))
                    if any(v is None for v in (o,h,l,c)) or float(c)<=0: continue
                    rows.append({'date':datetime.fromtimestamp(ts,timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('Asia/Seoul')).strftime('%m-%d %H:%M'), 'open':round(float(o),5),'high':round(float(h),5),'low':round(float(l),5),'close':round(float(c),5),'volume':int((q.get('volume') or [0]*len(timestamps))[i] or 0)})
                except (IndexError,TypeError,ValueError):continue
            if not rows:raise ValueError('유효한 분봉 데이터가 없습니다')
            if interval=='3m':rows=aggregate(rows,3,1)
            if interval=='240m':rows=aggregate(rows,4,60)
            return {'status':'ok','ticker':ticker,'interval_label':interval[:-1]+'분' if interval!='240m' else '4시간','updated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'source':'Yahoo Finance 비공식 데이터 · 지연 가능','series':rows[-350:]}
        except Exception as e:last_error=str(e)[:180]
    raise ValueError(last_error)

def aggregate(rows,count,base):
    # Aggregate consecutive source bars within each local trading date, rather than crossing sessions.
    out=[];bucket=[];day=None
    for row in rows:
        date=row['date'].split(' ')[0]
        if day!=date or len(bucket)>=count:
            if bucket:out.append(combine(bucket))
            bucket=[];day=date
        bucket.append(row)
    if bucket:out.append(combine(bucket))
    return out

def combine(items):
    return {'date':items[-1]['date'],'open':items[0]['open'],'high':max(x['high'] for x in items),'low':min(x['low'] for x in items),'close':items[-1]['close'],'volume':sum(x['volume'] for x in items)}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p=parse_qs(urlparse(self.path).query)
        ticker=p.get('ticker',[''])[0].upper().strip()
        interval=p.get('interval',['5m'])[0]
        market=p.get('market',['US'])[0].upper()
        try:
            if interval not in INTERVALS:raise ValueError('지원하지 않는 분봉 간격')
            if market not in ('US','KR'):raise ValueError('지원하지 않는 시장')
            if not re.fullmatch(r'[A-Z0-9.\-]{1,18}',ticker):raise ValueError('종목 식별값 오류')
            if market=='KR' and not re.fullmatch(r'\d{6}\.(KS|KQ)',ticker):raise ValueError('한국 종목 식별값 오류')
            body=fetch(ticker,interval);code=200
        except Exception as e:body={'status':'error','error':str(e)[:220]};code=502
        raw=json.dumps(body,ensure_ascii=False).encode('utf-8')
        self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','public, s-maxage=45, stale-while-revalidate=60');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
