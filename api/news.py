"""Fetch public RSS headlines once daily; links go to original articles."""
import json, re
from pathlib import Path
from datetime import datetime,timezone
from xml.etree import ElementTree as ET
import requests
out=Path('data/news.json');out.parent.mkdir(exist_ok=True)
try:
    url='https://news.google.com/rss/search?q=미국+증시+나스닥+S%26P500+when%3A1d&hl=ko&gl=KR&ceid=KR:ko'
    r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=25);r.raise_for_status()
    root=ET.fromstring(r.content);items=[]
    for item in root.findall('.//channel/item')[:15]:
        title=re.sub(r'\s+',' ',item.findtext('title','')).strip()
        link=item.findtext('link','').strip()
        if title and link.startswith('https://'): items.append({'title':title,'url':link,'published':item.findtext('pubDate','')})
    if not items: raise RuntimeError('No news returned')
    data={'status':'ok','updated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'items':items,'source':'Google News RSS'}
except Exception as e:
    data={'status':'error','updated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'error':str(e),'items':[]}
out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
