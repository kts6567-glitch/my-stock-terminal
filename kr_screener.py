"""무료 Yahoo Finance 비공식 데이터로 국내 대표종목 표본을 일봉 스캔.
전체 코스피/코스닥 전수 스캔이 아님. 실패 시 기존 정상 JSON을 보존.
"""
from pathlib import Path
from datetime import datetime, timezone
import json, time
import yfinance as yf
from screener import calc

UNIVERSE = {
 '반도체 / AI': [('005930.KS','삼성전자'),('000660.KS','SK하이닉스'),('042700.KS','한미반도체'),('058470.KQ','리노공업'),('403870.KQ','HPSP'),('036930.KQ','주성엔지니어링')],
 '이차전지 / 소재': [('373220.KS','LG에너지솔루션'),('006400.KS','삼성SDI'),('051910.KS','LG화학'),('247540.KQ','에코프로비엠'),('086520.KQ','에코프로'),('066970.KS','엘앤에프')],
 '바이오 / 헬스케어': [('207940.KS','삼성바이오로직스'),('068270.KS','셀트리온'),('196170.KQ','알테오젠'),('028300.KQ','HLB'),('145020.KQ','휴젤')],
 '자동차 / 로봇': [('005380.KS','현대차'),('000270.KS','기아'),('012330.KS','현대모비스'),('454910.KS','두산로보틱스'),('277810.KQ','레인보우로보틱스')],
 '인터넷 / 플랫폼': [('035420.KS','NAVER'),('035720.KS','카카오'),('259960.KS','크래프톤'),('263750.KQ','펄어비스'),('251270.KS','넷마블')],
 '금융': [('105560.KS','KB금융'),('055550.KS','신한지주'),('086790.KS','하나금융지주'),('316140.KS','우리금융지주'),('024110.KS','기업은행')],
 '방산 / 조선': [('012450.KS','한화에어로스페이스'),('329180.KS','HD현대중공업'),('042660.KS','한화오션'),('010140.KS','삼성중공업'),('047810.KS','한국항공우주')],
 '전력 / 에너지': [('015760.KS','한국전력'),('034020.KS','두산에너빌리티'),('267260.KS','HD현대일렉트릭'),('010120.KS','LS ELECTRIC'),('096770.KS','SK이노베이션')],
}
OUT=Path('data/kr');OUT.mkdir(parents=True,exist_ok=True)

def save(name,payload):
 (OUT/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
 symbols={t:n for rows in UNIVERSE.values() for t,n in rows}
 scanned=set();bb=[];ma=[];vol=[];reports={};errors=[]
 for i in range(0,len(symbols),10):
  batch=list(symbols)[i:i+10]
  try:
   df=yf.download(batch,period='18mo',interval='1d',auto_adjust=True,progress=False,threads=False,timeout=35)
   for ticker in batch:
    try:
     item=calc(df,ticker)
     if not item:continue
     scanned.add(ticker);b,m,v,rep=item
     rep['company']=symbols[ticker];rep['market']='KR';rep['currency']='KRW'
     reports[ticker]=rep
     if b:bb.append({**b,'company':symbols[ticker]})
     ma.extend({**x,'company':symbols[ticker]} for x in m)
     if v:vol.append({**v,'company':symbols[ticker]})
    except Exception as e:errors.append(f'{ticker}: {str(e)[:90]}')
  except Exception as e:errors.append(f'batch {i}: {str(e)[:100]}')
  time.sleep(1)
 if len(scanned)<max(10,int(len(symbols)*0.55)):
  raise RuntimeError(f'한국 대표종목 데이터 부족: {len(scanned)}/{len(symbols)}. 기존 정상 데이터 유지. '+str(errors[:3]))
 common={'status':'ok','updated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'universe':'한국 대표종목 표본 (코스피·코스닥 전수 아님)','universe_count':len(symbols),'scanned_count':len(scanned),'source':'Yahoo Finance 비공식 일봉','price_basis':'수정 종가'}
 bb.sort(key=lambda x:x['breach_pct']);ma.sort(key=lambda x:-x['day_change_pct']);vol.sort(key=lambda x:-x['volume'])
 save('bollinger_top5.json',{**common,'threshold_pct':-3,'total_matches':len(bb),'results':bb[:5]})
 save('ma_bounce_top5.json',{**common,'results':ma[:5]})
 save('volume_top50.json',{**common,'as_of_date':vol[0]['date'] if vol else None,'results':vol[:50]})
 save('quant_reports.json',{**common,'results':reports})
 print('KR analyzed:',len(scanned),'/',len(symbols),'errors:',len(errors))

if __name__=='__main__':main()
