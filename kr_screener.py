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

# v16: match the ten-name Korean sector selection in the UI.
UNIVERSE['반도체 / AI'].extend([('000990.KS', 'DB하이텍'), ('009150.KS', '삼성전기'), ('240810.KQ', '원익IPS'), ('039030.KQ', '이오테크닉스'), ('005290.KQ', '동진쎄미켐')])
UNIVERSE['이차전지 / 소재'].extend([('003670.KS', '포스코퓨처엠'), ('005490.KS', 'POSCO홀딩스'), ('096770.KS', 'SK이노베이션'), ('011790.KS', 'SKC')])
UNIVERSE['바이오 / 헬스케어'].extend([('326030.KS', 'SK바이오팜'), ('128940.KS', '한미약품'), ('000100.KS', '유한양행'), ('302440.KS', 'SK바이오사이언스'), ('141080.KQ', '리가켐바이오')])
UNIVERSE['자동차 / 로봇'].extend([('204320.KS', 'HL만도'), ('018880.KS', '한온시스템'), ('064350.KS', '현대로템'), ('108490.KQ', '로보티즈'), ('090360.KQ', '로보스타')])
UNIVERSE['인터넷 / 플랫폼'].extend([('036570.KS', '엔씨소프트'), ('112040.KQ', '위메이드'), ('078340.KQ', '컴투스'), ('041510.KQ', '에스엠'), ('352820.KS', '하이브')])
UNIVERSE['금융'].extend([('138040.KS', '메리츠금융지주'), ('175330.KS', 'JB금융지주'), ('139130.KS', 'DGB금융지주'), ('032830.KS', '삼성생명'), ('071050.KS', '한국금융지주')])
UNIVERSE['방산 / 조선'].extend([('272210.KS', '한화시스템'), ('079550.KS', 'LIG넥스원'), ('097230.KS', 'HJ중공업'), ('267250.KS', 'HD현대'), ('064350.KS', '현대로템')])
UNIVERSE['전력 / 에너지'].extend([('298040.KS', '효성중공업'), ('103590.KS', '일진전기'), ('001440.KS', '대한전선'), ('006260.KS', 'LS'), ('022100.KQ', '포스코DX')])
for group in UNIVERSE: UNIVERSE[group]=UNIVERSE[group][:10]
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
 merged={}
 for item in ma:
  t=item['ticker']
  if t not in merged: merged[t]={**item,'ma_periods':[]}
  if item['ma'] not in merged[t]['ma_periods']:merged[t]['ma_periods'].append(item['ma'])
 ma=list(merged.values())
 save('bollinger_top5.json',{**common,'threshold_pct':-3,'total_matches':len(bb),'results':bb[:5]})
 save('ma_bounce_top5.json',{**common,'results':ma[:5]})
 save('volume_top50.json',{**common,'as_of_date':vol[0]['date'] if vol else None,'results':sorted({v['ticker']:v for period in ('volume','volume_1w','volume_1m') for v in sorted(vol,key=lambda x:-x.get(period,0))[:50]}.values(),key=lambda x:-x['volume'])})
 save('quant_reports.json',{**common,'results':reports})
 print('KR analyzed:',len(scanned),'/',len(symbols),'errors:',len(errors))

if __name__=='__main__':main()
