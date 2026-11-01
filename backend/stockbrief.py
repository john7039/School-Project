"""임의 종목의 AI 브리핑을 그 자리에서 만든다.

매일 아침 company_curate.py 가 7종목을 미리 분석해 둔다. 하지만 사용자가
검색하는 종목은 미리 알 수 없어서, 7종목 밖이면 물어볼 때 만들어야 한다.
단어 검색(/api/news/pick)이 처음 보는 단어를 그 자리에서 분석하는 것과 같다.

흐름 — 뉴스 받아오기 → 수치 붙이기 → AI 한 번 → company_daily 에 저장.
저장하므로 같은 종목을 두 번째로 검색하는 사람은 기다리지 않는다.

이 모듈은 HTTP 응답을 붙잡고 있지 않다. main.py 가 백그라운드 스레드로
던지고 화면이 몇 초마다 다시 물어본다. 분석 하나에 외부 모델로 5~8초,
서버 안 모델로 100초가 걸려서, 응답을 기다리게 하면 중간 장비가 60초에
연결을 끊는다 — 단어 검색에서 실제로 당한 일이다.
"""
import datetime
import json
import os
import re
import sqlite3

from dotenv import load_dotenv

from llm import generate_json
from newsfilter import is_junk

load_dotenv()
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")

NEWS_DAYS = 7      # 며칠치 뉴스를 재료로 쓰나
NEWS_MAX = 5       # AI 에게 보여줄 제목 수 (company_curate.py 와 같게)


def _fetch_korea_news(name):
    """한국 종목 뉴스 — Google 뉴스 RSS(한국어).

    Finnhub 는 한국 상장을 거의 안 다룬다. 005930.KS 로 물어보면 0건이다.
    단어 검색에서 '현대차' 가 0건이던 것과 같은 문제고, 그때 만든
    rss_search.fetch() 가 이미 한국어 기사를 받아온다. 그대로 쓴다.

    회사 이름으로 찾는다 — 종목 코드로는 기사가 안 걸린다.
    """
    try:
        import rss_search
        rows = rss_search.fetch(name, days=NEWS_DAYS)
    except Exception as e:
        print(f"  한국 뉴스 받기 실패 {name}: {e.__class__.__name__} — 수치만으로 진행")
        return []
    out = []
    for title, _src, _stamp, _url in rows:
        title = (title or "").strip()
        if not title or is_junk(title):
            continue
        out.append(title)
        if len(out) >= NEWS_MAX:
            break
    return out


def _fetch_company_news(ticker):
    """Finnhub 종목 뉴스. 실패하면 빈 목록 — 수치만으로도 브리핑은 만든다."""
    if not FINNHUB_KEY:
        print("  FINNHUB_KEY 없음 — 뉴스 없이 진행")
        return []
    import urllib.request
    today = datetime.date.today()
    frm = (today - datetime.timedelta(days=NEWS_DAYS)).isoformat()
    url = (f"https://finnhub.io/api/v1/company-news?symbol={ticker}"
           f"&from={frm}&to={today.isoformat()}&token={FINNHUB_KEY}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        arr = json.loads(urllib.request.urlopen(req, timeout=25).read())
    except Exception as e:
        print(f"  뉴스 받기 실패 {ticker}: {e.__class__.__name__} — 수치만으로 진행")
        return []
    if not isinstance(arr, list):
        return []
    arr = sorted(arr, key=lambda a: a.get("datetime", 0), reverse=True)
    out = []
    for a in arr:
        title = (a.get("headline") or "").strip()
        if not title or is_junk(title):
            continue
        out.append(title)
        if len(out) >= NEWS_MAX:
            break
    return out


def _flow(change):
    if change is None:
        return "알 수 없음"
    if change > 0.5:
        return "상승 + 거래 활발 → 매수세"
    if change < -0.5:
        return "하락 + 거래 → 매도세"
    return "보합"


def _prompt(name, ticker, date, close, change, volume, titles, vol_note=None,
            currency="USD"):
    """company_curate.py 의 프롬프트와 같은 모양을 유지한다.

    모양이 어긋나면 미리 분석한 7종목과 검색으로 만든 종목의 말투가 달라져서,
    사용자는 같은 화면에서 두 사람이 쓴 글을 읽게 된다.
    """
    numbered = "\n".join(f"  [{j}] {t}" for j, t in enumerate(titles)) or "  (없음)"
    n_last = max(len(titles) - 1, 0)
    keys_hint = ", ".join(f'"{j}": "긍정|부정|중립"'
                          for j in range(len(titles))) or '"(없음)"'
    vol_txt = f"거래량 {volume:,}" if volume else "거래량 미확인"
    if volume and vol_note:
        vol_txt += f" ({vol_note})"
    chg_txt = f"전일 대비 {change}%" if change is not None else "전일 대비 미확인"
    cur = (currency or "USD").upper()
    unit = {"USD": "달러", "KRW": "원"}.get(cur, cur)
    where = "한국 상장" if cur == "KRW" else "미국 상장"
    shown = f"{close:,}" if isinstance(close, (int, float)) else close
    return f"""{name}({ticker})의 {date} 주식 상황이다. {where} 종목이고 금액 단위는 {unit}다.
종가 {shown}{unit}, {chg_txt}, {vol_txt}. (추정 흐름: {_flow(change)})
관련 뉴스(번호순):
{numbered}

경제 초보자에게 "오늘 이 회사가 어땠는지"를 2~3문장으로 쉽게 설명하라.
매수세/매도세는 거래량과 등락으로 추정해 표현하고, 뉴스가 있으면 왜 그렇게 움직였는지 연결하라.
뉴스가 없으면 수치만으로 설명하고, 없는 이유를 추측해 쓰지 마라.
**거래량이 많다/적다는 위에 적힌 비교만 근거로 쓰고, 비교가 없으면 거래량의 많고 적음을 언급하지 마라.**
**금액 단위는 {unit}다. 다른 통화로 바꿔 쓰지 마라.**
또한 위 뉴스 각각이 이 회사(주가)에 주는 영향을 분류하라. 판단 기준:
- 유리한 소식(실적 호조, 성장·수요 증가, 호재, 파트너십, 신제품 등) → '긍정'
- 불리한 소식(실적 부진, 규제·소송·악재, 수요 둔화, 경쟁 심화 등) → '부정'
- 이 회사와 무관하거나 방향이 정말 불분명할 때만 → '중립'
**대부분을 중립으로 몰지 말고, 조금이라도 유불리가 보이면 긍정/부정으로 적극 판단하라.**
아래 JSON 형식으로만 한국어로 답하라. news_sentiments는 뉴스 번호(0~{n_last})를 key로, 각 값은 반드시 "긍정"/"부정"/"중립" 문자열 중 하나로 채운 객체다(숫자 금지, 모든 번호 포함):
{{"ai_summary": "<초보자용 설명>",
  "news_sentiments": {{{keys_hint}}}}}"""


# 미국 주식 금액을 '원' 으로 쓴 것을 잡는다.
#
# 프롬프트에 "달러다" 라고 써도 모델이 어기는 때가 있다. 운영 DB 의 과거
# 분석 218건 중 1건이 그랬다 (META 612.49원). 드물어서 눈에 안 띄고, 눈에
# 안 띄는 틀린 숫자가 화면에 그대로 남는다.
# 환율 해설에서 방향을 거꾸로 쓴 것을 wrong_direction() 으로 잡은 것과 같다.
#
# 조사도 같이 바꿔야 한다 — '원' 은 받침이 있고 '달러' 는 없다.
# 그냥 치환하면 "365.87달러으로" 가 되어 문장이 깨진다.
_WON = re.compile(r"(\d[\d,.]*)\s*원(으로|이|은|을|과)?")
_PARTICLE = {"으로": "로", "이": "가", "은": "는", "을": "를", "과": "와"}


def fix_currency(text):
    """'612.49원으로' → '612.49달러로'. 바꾼 게 있으면 (고친글, True)."""
    def rep(m):
        p = m.group(2) or ""
        return m.group(1) + "달러" + _PARTICLE.get(p, p)
    fixed, n = _WON.subn(rep, text or "")
    return fixed, n > 0


def _sent_of(sents, j):
    v = None
    if isinstance(sents, dict):
        v = sents.get(str(j), sents.get(j))
    elif isinstance(sents, list) and j < len(sents):
        v = sents[j]
    v = v.strip() if isinstance(v, str) else ""
    return v if v in ("긍정", "부정", "중립") else "중립"


def ensure_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS company_daily (
      ticker TEXT, date TEXT, close REAL, change_pct REAL, volume INTEGER,
      news_json TEXT, ai_summary TEXT,
      PRIMARY KEY (ticker, date))""")
    conn.commit()


def build(ticker, name, quote, redo=False):
    """브리핑 한 건을 만들어 저장하고 돌려준다. 실패하면 예외를 올린다.

    quote 는 stockquote.quote() 결과. 날짜는 거기 담긴 trade_date(미 동부
    기준 거래일)를 쓴다 — 한국 시각으로 자르면 company_curate.py 가 쓰는
    날짜와 하루 어긋나서, 같은 장이 두 날짜로 쌓인다.
    """
    ticker = ticker.upper()
    date = quote.get("trade_date") or datetime.date.today().isoformat()

    conn = sqlite3.connect("econ.db")
    conn.row_factory = sqlite3.Row
    ensure_table(conn)

    if not redo:
        row = conn.execute(
            "SELECT * FROM company_daily WHERE ticker=? AND date=?",
            (ticker, date)).fetchone()
        if row:
            conn.close()
            return dict(row)

    is_kr = ticker.endswith((".KS", ".KQ")) or ticker.startswith("^KS") \
        or ticker.startswith("^KQ")
    titles = _fetch_korea_news(name) if is_kr else _fetch_company_news(ticker)
    close = quote.get("price")
    change = quote.get("pct")
    volume = quote.get("volume")

    # 거래량을 '많다/적다' 로 말하려면 비교 기준이 있어야 한다. 없으면
    # 모델이 지어낸다 (실제로 "거래량이 크게 늘어나면서" 라고 썼다).
    vol_note = None
    try:
        import stockquote
        vol_note = stockquote.volume_note(stockquote.history(ticker, 21), volume)
    except Exception as e:
        print(f"  거래량 비교 실패 {ticker}: {e.__class__.__name__} — 비교 없이 진행")

    currency = quote.get("currency") or "USD"
    prompt = _prompt(name, ticker, date, close, change, volume, titles,
                     vol_note, currency)
    data = generate_json(prompt)          # 실패하면 예외 → 호출한 쪽이 상태에 남긴다
    summary = (data.get("ai_summary") or "").strip()
    if not summary:
        conn.close()
        raise ValueError("ai_summary 가 비었다")

    if currency.upper() == "USD":
        summary, changed = fix_currency(summary)
        if changed:
            print(f"  {ticker}: 금액을 '원' 으로 쓴 것을 '달러' 로 고쳤다")

    sents = data.get("news_sentiments", {})
    news_list = [{"title": t, "sentiment": _sent_of(sents, j)}
                 for j, t in enumerate(titles)]

    conn.execute(
        "INSERT OR REPLACE INTO company_daily "
        "(ticker, date, close, change_pct, volume, news_json, ai_summary) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticker, date, close, change, volume,
         json.dumps(news_list, ensure_ascii=False), summary))
    conn.commit()
    row = conn.execute("SELECT * FROM company_daily WHERE ticker=? AND date=?",
                       (ticker, date)).fetchone()
    conn.close()
    print(f"{ticker} {date}: 브리핑 생성 (뉴스 {len(news_list)}건)")
    return dict(row)
