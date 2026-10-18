"""Monthly earnings + macro calendar. US earnings: Nasdaq day-wide feed.
Coverage is best-effort; Nasdaq public endpoint is unofficial and may block.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse,parse_qs,urlencode
from urllib.request import Request,urlopen
from datetime import date,datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,re
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36'

def get_json(url,timeout=5):
    req=Request(url,headers={'User-Agent':UA,'Accept':'application/json, text/plain, */*','Origin':'https://www.nasdaq.com','Referer':'https://www.nasdaq.com/'})
    with urlopen(req,timeout=timeout) as r:return json.loads(r.read(2500000))

def date_of(v):
    if not v:return None
    m=re.search(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})',str(v))
    if m:return f'{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}'
    return None

def rows(o):
    if isinstance(o,list):return o
    if isinstance(o,dict):
        for k in ('rows','events','data','results','items','calendar'):
            v=o.get(k)
            if isinstance(v,list):return v
            if isinstance(v,dict):
                r=rows(v)
                if r:return r
    return []

def macro(start,end):
    data=get_json('https://www.financecalendar.com/wp-json/fc/v1/calendar?'+urlencode({'from':start,'to':end,'limit':500}),timeout=7)
    out=[]
    for x in rows(data):
        if not isinstance(x,dict):continue
        day=date_of(x.get('date') or x.get('release_date') or x.get('datetime') or x.get('start'))
        title=str(x.get('title') or x.get('name') or x.get('event') or '').strip()
        if day and start<=day<=end and title:out.append({'date':day,'title':title[:150],'type':'macro','time':str(x.get('time') or '')[:24],'source':'FinanceCalendar'})
    return out

def nasdaq_day(day):
    d=get_json('https://api.nasdaq.com/api/calendar/earnings?'+urlencode({'date':day}),timeout=5)
    data=d.get('data') if isinstance(d,dict) else {}
    result=[]
    for x in rows(data):
        if not isinstance(x,dict):continue
        symbol=str(x.get('symbol') or x.get('ticker') or '').strip().upper()
        if not re.fullmatch(r'[A-Z0-9.\-]{1,16}',symbol):continue
        name=str(x.get('name') or x.get('company') or symbol)[:110]
        when=str(x.get('time') or x.get('timeOfDay') or '').strip()
        result.append({'date':day,'title':name+' 실적 발표 (예정)','ticker':symbol,'type':'earnings','time':when[:35],'source':'Nasdaq'})
    return result

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q=parse_qs(urlparse(self.path).query)
        today=datetime.now(timezone.utc).date()
        start=q.get('from',[today.isoformat()])[0];end=q.get('to',[(today+timedelta(days=30)).isoformat()])[0]
        market=q.get('market',['US'])[0].upper()
        fetch_earnings=q.get('earnings',['1'])[0]!='0'
        fetch_macro=q.get('macro',['1'])[0]!='0'
        try:
            a,b=date.fromisoformat(start),date.fromisoformat(end)
            if b<a or (b-a).days>34:raise ValueError('최대 35일 범위로 조회해주세요.')
            warnings=[];events=[];okdays=0;totaldays=0
            if fetch_macro:
                try:events.extend(macro(start,end))
                except Exception:warnings.append('경제 일정 수집 실패 또는 제공처 차단')
            if market=='US' and fetch_earnings:
                days=[(a+timedelta(days=i)).isoformat() for i in range((b-a).days+1) if (a+timedelta(days=i)).weekday()<5]
                totaldays=len(days)
                # Parallel bounded calls: one daily endpoint includes all Nasdaq-listed reported companies.
                with ThreadPoolExecutor(max_workers=5) as pool:
                    futures={pool.submit(nasdaq_day,d):d for d in days}
                    for f in as_completed(futures):
                        try:events.extend(f.result());okdays+=1
                        except Exception:pass
                if okdays<totaldays:warnings.append(f'미국 실적: {okdays}/{totaldays}거래일 조회 성공 · 나머지 일정 누락 가능')
            elif market!='US' and fetch_earnings:warnings.append('한국 전체 기업 실적 일정 제공처 미연결')
            unique={ (e['date'],e['type'],e.get('ticker',e['title'])):e for e in events }
            events=sorted(unique.values(),key=lambda x:(x['date'],x['type'],x['title']))
            payload={'status':'ok','events':events,'warnings':warnings,'coverage':{'market':market,'earnings_days_success':okdays,'earnings_days_requested':totaldays,'complete':market=='US' and totaldays>0 and okdays==totaldays},'updated_at_utc':datetime.now(timezone.utc).isoformat()}
            status=200
        except Exception as e:payload={'status':'error','error':str(e)};status=400
        body=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','s-maxage=3600, stale-while-revalidate=1800');self.end_headers();self.wfile.write(body)
