"""Best-effort per-stock Google News RSS proxy for Vercel. No API key."""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
import json, re

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            p=parse_qs(urlparse(self.path).query)
            name=(p.get('name') or [''])[0].strip()[:90]
            ticker=(p.get('ticker') or [''])[0].strip()[:20]
            market=(p.get('market') or ['US'])[0]
            if not name or not re.match(r'^[\w.\-\s가-힣&]+$',name):raise ValueError('종목명이 올바르지 않습니다.')
            term=(name+' 주가') if market=='KR' else (name+' '+ticker+' stock')
            url='https://news.google.com/rss/search?'+urlencode({'q':term+' when:14d','hl':'ko','gl':'KR','ceid':'KR:ko'})
            req=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; PersonalDashboard/1.0)'})
            with urlopen(req,timeout=9) as r: xml=r.read(350000)
            root=ET.fromstring(xml);items=[]
            for item in root.findall('./channel/item')[:12]:
                title=' '.join((item.findtext('title') or '').split())
                link=(item.findtext('link') or '').strip()
                if title and link.startswith('https://'):
                    items.append({'title':title,'url':link,'published':item.findtext('pubDate') or ''})
            result={'status':'ok','items':items,'source':'Google News RSS'}
            self.send_response(200)
        except Exception as e:
            result={'status':'error','error':str(e)[:180],'items':[]};self.send_response(502)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','public, s-maxage=600, stale-while-revalidate=1200')
        self.end_headers();self.wfile.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
