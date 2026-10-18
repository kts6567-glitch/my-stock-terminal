"""Public, keyless event calendar proxy for Vercel Python functions.
Events are best-effort; never claim a missing event means none is scheduled.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from datetime import datetime, date, timedelta, timezone
import json
import urllib.request
import re

UA = 'Mozilla/5.0 (compatible; JHMarketTrade/1.0; personal research)'

def get_json(url, timeout=9):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept':'application/json, text/plain, */*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200: raise RuntimeError('upstream HTTP '+str(r.status))
        return json.loads(r.read(1500000).decode('utf-8'))

def as_date(value):
    if not value: return None
    if isinstance(value,(int,float)):
        try:return datetime.fromtimestamp(value,timezone.utc).date().isoformat()
        except Exception:return None
    s=str(value)
    x=re.search(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})',s)
    if x:return f'{int(x.group(1)):04d}-{int(x.group(2)):02d}-{int(x.group(3)):02d}'
    x=re.search(r'(\d{1,2})/(\d{1,2})/(20\d{2})',s)
    if x:return f'{int(x.group(3)):04d}-{int(x.group(1)):02d}-{int(x.group(2)):02d}'
    return None

def rows(obj):
    if isinstance(obj,list):return obj
    if not isinstance(obj,dict):return []
    for k in ('events','data','results','items','calendar','rows'):
        v=obj.get(k)
        if isinstance(v,list):return v
        if isinstance(v,dict):
            r=rows(v)
            if r:return r
    return []

def economic(start,end):
    url='https://www.financecalendar.com/wp-json/fc/v1/calendar?'+urlencode({'from':start,'to':end,'limit':500})
    data=get_json(url)
    out=[]
    for x in rows(data):
        if not isinstance(x,dict):continue
        day=as_date(x.get('date') or x.get('release_date') or x.get('datetime') or x.get('start') or x.get('scheduled_at'))
        title=str(x.get('title') or x.get('name') or x.get('event') or x.get('series') or '').strip()
        if not day or not title or not(start<=day<=end):continue
        impact=str(x.get('impact') or x.get('importance') or '').lower()
        if impact and impact not in ('high','medium','3','2','critical'):continue
        out.append({'date':day,'title':title[:150],'type':'macro','time':str(x.get('time') or '')[:32], 'source':'FinanceCalendar'})
    return out

def earnings(start,end,ticker):
    # Nasdaq public calendar is a best-effort source; do not silently invent dates.
    out=[]
    if not ticker or not re.fullmatch(r'[A-Z0-9.\-]{1,12}',ticker):return out
    day=date.fromisoformat(start)
    last=date.fromisoformat(end)
    # Request per day only for a short horizon, bounded to protect serverless time.
    if (last-day).days>12:return out
    while day<=last:
        ds=day.strftime('%Y-%m-%d')
        url='https://api.nasdaq.com/api/calendar/earnings?'+urlencode({'date':ds})
        try:
            d=get_json(url,timeout=4)
            data=d.get('data',{}) if isinstance(d,dict) else {}
            records=rows(data)
            if not records and isinstance(data,dict):records=rows(data.get('rows',[]))
            for r in records:
                if not isinstance(r,dict):continue
                symbol=str(r.get('symbol') or r.get('ticker') or '').upper()
                if symbol!=ticker:continue
                out.append({'date':ds,'title':str(r.get('name') or r.get('company') or ticker)+' 실적 발표 (예정)','ticker':ticker,'type':'earnings','source':'Nasdaq'})
        except Exception:pass
        day+=timedelta(days=1)
    return out

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs=parse_qs(urlparse(self.path).query)
        today=datetime.now(timezone.utc).date()
        start=qs.get('from',[today.isoformat()])[0]
        end=qs.get('to',[(today+timedelta(days=30)).isoformat()])[0]
        ticker=qs.get('ticker',[''])[0].upper().strip()
        try:
            a,b=date.fromisoformat(start),date.fromisoformat(end)
            if b<a or (b-a).days>45:raise ValueError('조회 범위는 최대 45일입니다.')
            warnings=[]
            try:events=economic(start,end)
            except Exception as e:events=[];warnings.append('경제 일정 제공처 조회 실패: '+str(e)[:100])
            if ticker:
                # Only look up individual earnings for short horizons; monthly calendar is macro+user events.
                er=earnings(start,end,ticker)
                events.extend(er)
                if not er:warnings.append('선택 종목 실적 일정은 확인되지 않았습니다. 공식 IR에서 재확인하세요.')
            events.sort(key=lambda e:(e['date'],e['title']))
            payload={'status':'ok','events':events,'warnings':warnings,'updated_at_utc':datetime.now(timezone.utc).isoformat(),'coverage':'best-effort, not exhaustive'}
            status=200
        except Exception as e:
            payload={'status':'error','error':str(e)};status=400
        body=json.dumps(payload,ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','s-maxage=900, stale-while-revalidate=600')
        self.end_headers();self.wfile.write(body)
