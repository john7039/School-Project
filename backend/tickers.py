"""종목 검색어를 티커로 바꿔주는 사전.

search_terms.py 가 한국어 검색어를 영어 표현으로 넓히는 것과 같은 역할을
종목에 대해 한다. 사용자는 "엔비디아" 라고 치는데 데이터는 전부 NVDA 로
들어 있어서, 그대로는 한 건도 안 걸린다.

세 가지를 받아준다 —
  1) 한글 이름      엔비디아 · 애플 · 테슬라
  2) 영문 이름      nvidia · apple · tesla
  3) 티커 그대로     NVDA · nvda

사전에 없는 티커는 resolve() 가 '후보' 로만 돌려주고, 실제로 있는 종목인지는
yfinance 가 판정한다. 사전을 무한히 늘리지 않으려는 것이다 — 미국 상장만
수천 개다.

⚠️ 미국 상장 종목만 다룬다. 주가(yfinance)는 한국 종목도 되지만 뉴스를
Finnhub 에서 받아서 국내 기업은 기사가 거의 없다. 뉴스 없는 종목은 AI 가
설명할 재료가 없어서 "주가만 있는 빈 화면" 이 된다. 범위를 넓히려면
한글 뉴스 수집 경로(Google News RSS)를 먼저 붙여야 한다.
"""

# 티커 -> 화면에 쓸 한글 이름
NAMES = {
    # 매일 미리 분석하는 7종목 (company_curate.py 와 같아야 한다)
    "AAPL": "애플", "MSFT": "마이크로소프트", "NVDA": "엔비디아",
    "AMZN": "아마존", "GOOGL": "알파벳(구글)", "TSLA": "테슬라", "META": "메타",
    # 반도체
    "AMD": "AMD", "INTC": "인텔", "TSM": "TSMC", "AVGO": "브로드컴",
    "MU": "마이크론", "QCOM": "퀄컴", "ARM": "ARM", "SMCI": "슈퍼마이크로",
    "ASML": "ASML", "LRCX": "램리서치",
    # 소프트웨어·플랫폼
    "ORCL": "오라클", "CRM": "세일즈포스", "ADBE": "어도비", "IBM": "IBM",
    "CSCO": "시스코", "NFLX": "넷플릭스", "PLTR": "팔란티어", "SHOP": "쇼피파이",
    "SNOW": "스노우플레이크", "UBER": "우버", "ABNB": "에어비앤비",
    "COIN": "코인베이스", "SPOT": "스포티파이",
    # 소비·유통
    "WMT": "월마트", "COST": "코스트코", "HD": "홈디포", "NKE": "나이키",
    "SBUX": "스타벅스", "MCD": "맥도날드", "KO": "코카콜라", "PEP": "펩시코",
    "DIS": "디즈니",
    # 금융
    "JPM": "JP모건", "BAC": "뱅크오브아메리카", "V": "비자", "MA": "마스터카드",
    "GS": "골드만삭스", "BRK-B": "버크셔해서웨이",
    # 제조·에너지·항공
    "BA": "보잉", "LMT": "록히드마틴", "CAT": "캐터필러", "GE": "GE",
    "XOM": "엑슨모빌", "CVX": "셰브론", "F": "포드", "GM": "GM",
    # 헬스케어
    "JNJ": "존슨앤존슨", "PFE": "화이자", "LLY": "일라이릴리",
    "UNH": "유나이티드헬스", "MRNA": "모더나", "ABBV": "애브비",
    # 지수 ETF — 초보자가 '나스닥', 'S&P' 로 많이 찾는다
    "QQQ": "나스닥100 ETF", "SPY": "S&P500 ETF", "DIA": "다우존스 ETF",
    # themes.py 가 쓰는 종목들
    "COP": "코노코필립스", "SLB": "슐럼버거", "RIVN": "리비안",
    "RTX": "RTX", "NOC": "노스롭그루먼", "SOXX": "반도체 ETF",
    # 에너지 — 해외 메이저는 뉴욕 상장 ADR 로 받는다. 달러로 거래되고
    # 뉴스도 잡힌다. 사우디 아람코(2222.SR)는 리얄 표시라 넣지 않았다.
    "SHEL": "셸", "BP": "BP", "TTE": "토탈에너지스", "EQNR": "에퀴노르",
    "PBR": "페트로브라스", "OXY": "옥시덴탈",
    # 반도체
    "AMAT": "어플라이드머티리얼즈",
    # 자동차
    "TM": "토요타", "HMC": "혼다", "STLA": "스텔란티스",
    "LCID": "루시드", "NIO": "니오",
    # 금융
    "WFC": "웰스파고", "C": "씨티그룹", "MS": "모건스탠리",
    "AXP": "아메리칸익스프레스", "BLK": "블랙록",
    # 소비
    "PG": "P&G", "TGT": "타겟",
    # 헬스케어
    "MRK": "머크", "TMO": "써모피셔", "BMY": "브리스톨마이어스",
    "AMGN": "암젠", "NVO": "노보노디스크",
    # 방산
    "GD": "제너럴다이내믹스", "LHX": "L3해리스", "HII": "헌팅턴인갈스",
    # 지수 ETF
    "IWM": "러셀2000 ETF", "VTI": "미국전체 ETF",

    # ── 한국 상장 (KRX) ──────────────────────────────
    # 야후는 '005930.KS' 꼴로 받는다. 가격이 원화라 통화 처리가 필요하고,
    # 뉴스는 Finnhub 가 아니라 Google 뉴스 RSS(한국어)에서 받는다.
    "005930.KS": "삼성전자", "000660.KS": "SK하이닉스",
    "373220.KS": "LG에너지솔루션", "207940.KS": "삼성바이오로직스",
    "005380.KS": "현대차", "000270.KS": "기아",
    "035420.KS": "NAVER", "035720.KS": "카카오",
    "051910.KS": "LG화학", "006400.KS": "삼성SDI",
    "005490.KS": "포스코홀딩스", "105560.KS": "KB금융",
    "055550.KS": "신한지주", "086790.KS": "하나금융지주",
    "012330.KS": "현대모비스", "068270.KS": "셀트리온",
    "028260.KS": "삼성물산", "066570.KS": "LG전자",
    "015760.KS": "한국전력", "009540.KS": "HD한국조선해양",
    "042660.KS": "한화오션", "012450.KS": "한화에어로스페이스",
    "003490.KS": "대한항공", "017670.KS": "SK텔레콤",
    "030200.KS": "KT", "032640.KS": "LG유플러스",
    "^KS11": "코스피", "^KQ11": "코스닥",
}

# 검색어 -> 티커. 소문자·공백제거 후 비교한다.
_EXTRA = {
    "애플": "AAPL", "apple": "AAPL", "아이폰": "AAPL",
    "마이크로소프트": "MSFT", "microsoft": "MSFT", "엠에스": "MSFT", "ms": "MSFT",
    "엔비디아": "NVDA", "nvidia": "NVDA", "앤비디아": "NVDA", "엔비디야": "NVDA",
    "아마존": "AMZN", "amazon": "AMZN",
    "구글": "GOOGL", "google": "GOOGL", "알파벳": "GOOGL", "유튜브": "GOOGL",
    "테슬라": "TSLA", "tesla": "TSLA", "머스크": "TSLA", "테스라": "TSLA",
    "메타": "META", "meta": "META", "페이스북": "META", "facebook": "META",
    "인스타그램": "META", "인스타": "META",
    "에이엠디": "AMD", "암드": "AMD",
    "인텔": "INTC", "intel": "INTC",
    "티에스엠씨": "TSM", "tsmc": "TSM", "대만반도체": "TSM",
    "브로드컴": "AVGO", "broadcom": "AVGO",
    "마이크론": "MU", "micron": "MU",
    "퀄컴": "QCOM", "qualcomm": "QCOM",
    "암": "ARM", "에이알엠": "ARM",
    "슈퍼마이크로": "SMCI", "슈마컴": "SMCI",
    "에이에스엠엘": "ASML",
    "램리서치": "LRCX",
    "오라클": "ORCL", "oracle": "ORCL",
    "세일즈포스": "CRM", "salesforce": "CRM",
    "어도비": "ADBE", "adobe": "ADBE", "포토샵": "ADBE",
    "아이비엠": "IBM",
    "시스코": "CSCO", "cisco": "CSCO",
    "넷플릭스": "NFLX", "netflix": "NFLX",
    "팔란티어": "PLTR", "palantir": "PLTR", "팔란티르": "PLTR",
    "쇼피파이": "SHOP", "shopify": "SHOP",
    "스노우플레이크": "SNOW",
    "우버": "UBER", "uber": "UBER",
    "에어비앤비": "ABNB", "airbnb": "ABNB",
    "코인베이스": "COIN", "coinbase": "COIN",
    "스포티파이": "SPOT", "spotify": "SPOT",
    "월마트": "WMT", "walmart": "WMT",
    "코스트코": "COST", "costco": "COST",
    "홈디포": "HD",
    "나이키": "NKE", "nike": "NKE",
    "스타벅스": "SBUX", "starbucks": "SBUX",
    "맥도날드": "MCD", "맥날": "MCD", "mcdonalds": "MCD",
    "코카콜라": "KO", "코카콜": "KO", "콜라": "KO", "cocacola": "KO",
    "펩시": "PEP", "펩시코": "PEP", "pepsi": "PEP",
    "디즈니": "DIS", "disney": "DIS",
    "제이피모건": "JPM", "jpmorgan": "JPM", "제피모건": "JPM",
    "뱅크오브아메리카": "BAC", "뱅크오브어메리카": "BAC", "bofa": "BAC",
    "비자": "V", "visa": "V",
    "마스터카드": "MA", "mastercard": "MA",
    "골드만삭스": "GS", "goldman": "GS", "골드먼삭스": "GS",
    "버크셔": "BRK-B", "버크셔해서웨이": "BRK-B", "버핏": "BRK-B",
    "berkshire": "BRK-B", "brkb": "BRK-B", "brk.b": "BRK-B",
    "보잉": "BA", "boeing": "BA",
    "록히드마틴": "LMT", "록히드": "LMT", "lockheed": "LMT",
    "캐터필러": "CAT",
    "지이": "GE",
    "엑슨모빌": "XOM", "엑손모빌": "XOM", "exxon": "XOM",
    "셰브론": "CVX", "쉐브론": "CVX", "chevron": "CVX",
    "포드": "F", "ford": "F",
    "지엠": "GM", "제너럴모터스": "GM",
    "존슨앤존슨": "JNJ", "존슨": "JNJ",
    "화이자": "PFE", "pfizer": "PFE",
    "일라이릴리": "LLY", "릴리": "LLY", "lilly": "LLY",
    "유나이티드헬스": "UNH",
    "모더나": "MRNA", "moderna": "MRNA",
    "애브비": "ABBV",
    "나스닥": "QQQ", "nasdaq": "QQQ", "나스닥100": "QQQ", "큐큐큐": "QQQ",
    "에스앤피": "SPY", "sp500": "SPY", "s&p500": "SPY", "s&p": "SPY",
    "스파이": "SPY", "미국지수": "SPY",
    "다우": "DIA", "다우존스": "DIA", "dow": "DIA",
    "코노코필립스": "COP", "코노코": "COP", "conoco": "COP",
    "슐럼버거": "SLB", "슐럼버제": "SLB",
    "리비안": "RIVN", "rivian": "RIVN",
    "알티엑스": "RTX", "레이시온": "RTX", "raytheon": "RTX",
    "노스롭그루먼": "NOC", "노스롭": "NOC", "northrop": "NOC",
    "셸": "SHEL", "쉘": "SHEL", "shell": "SHEL",
    "비피": "BP", "브리티시페트롤리움": "BP",
    "토탈": "TTE", "토탈에너지스": "TTE", "total": "TTE", "totalenergies": "TTE",
    "에퀴노르": "EQNR", "equinor": "EQNR", "스타토일": "EQNR",
    "페트로브라스": "PBR", "petrobras": "PBR",
    "옥시덴탈": "OXY", "옥시": "OXY", "occidental": "OXY",
    "어플라이드머티리얼즈": "AMAT", "어플라이드": "AMAT", "applied": "AMAT",
    "토요타": "TM", "도요타": "TM", "toyota": "TM",
    "혼다": "HMC", "honda": "HMC",
    "스텔란티스": "STLA", "stellantis": "STLA", "지프": "STLA",
    "루시드": "LCID", "lucid": "LCID",
    "니오": "NIO", "nio": "NIO",
    "웰스파고": "WFC", "wellsfargo": "WFC",
    "씨티": "C", "씨티그룹": "C", "citi": "C", "citigroup": "C",
    "모건스탠리": "MS", "morganstanley": "MS",
    "아메리칸익스프레스": "AXP", "아멕스": "AXP", "amex": "AXP",
    "블랙록": "BLK", "blackrock": "BLK",
    "피앤지": "PG", "프록터앤갬블": "PG", "pg": "PG",
    "타겟": "TGT", "타깃": "TGT", "target": "TGT",
    "머크": "MRK", "merck": "MRK",
    "써모피셔": "TMO", "서모피셔": "TMO", "thermo": "TMO",
    "브리스톨마이어스": "BMY", "브리스톨": "BMY",
    "암젠": "AMGN", "amgen": "AMGN",
    "노보노디스크": "NVO", "노보": "NVO", "위고비": "NVO", "novo": "NVO",
    "제너럴다이내믹스": "GD",
    "엘쓰리해리스": "LHX", "l3해리스": "LHX",
    "헌팅턴인갈스": "HII",
    "러셀": "IWM", "러셀2000": "IWM",
    "브이티아이": "VTI",

    # 한국 종목 — 사람들이 실제로 치는 말로
    "삼성전자": "005930.KS", "삼전": "005930.KS", "삼성": "005930.KS",
    "sk하이닉스": "000660.KS", "하이닉스": "000660.KS", "sk하닉": "000660.KS",
    "lg에너지솔루션": "373220.KS", "엘지엔솔": "373220.KS", "lg엔솔": "373220.KS",
    "삼성바이오로직스": "207940.KS", "삼바": "207940.KS",
    "현대차": "005380.KS", "현대자동차": "005380.KS",
    "기아": "000270.KS", "기아차": "000270.KS",
    "네이버": "035420.KS", "naver": "035420.KS",
    "카카오": "035720.KS", "kakao": "035720.KS",
    "lg화학": "051910.KS", "엘지화학": "051910.KS",
    "삼성sdi": "006400.KS", "삼성에스디아이": "006400.KS",
    "포스코": "005490.KS", "포스코홀딩스": "005490.KS", "posco": "005490.KS",
    "kb금융": "105560.KS", "국민은행": "105560.KS", "케이비금융": "105560.KS",
    "신한지주": "055550.KS", "신한은행": "055550.KS", "신한": "055550.KS",
    "하나금융": "086790.KS", "하나금융지주": "086790.KS", "하나은행": "086790.KS",
    "현대모비스": "012330.KS", "모비스": "012330.KS",
    "셀트리온": "068270.KS",
    "삼성물산": "028260.KS",
    "lg전자": "066570.KS", "엘지전자": "066570.KS",
    "한국전력": "015760.KS", "한전": "015760.KS",
    "hd한국조선해양": "009540.KS", "한국조선해양": "009540.KS",
    "한화오션": "042660.KS", "대우조선": "042660.KS",
    "한화에어로스페이스": "012450.KS", "한화에어로": "012450.KS",
    "대한항공": "003490.KS",
    "sk텔레콤": "017670.KS", "skt": "017670.KS",
    "kt": "030200.KS", "케이티": "030200.KS",
    "lg유플러스": "032640.KS", "엘지유플러스": "032640.KS",
    "코스피": "^KS11", "kospi": "^KS11",
    "코스닥": "^KQ11", "kosdaq": "^KQ11",
}

# 사전에서 자동으로 만들 수 있는 것은 자동으로 (티커 그대로, 한글 이름 그대로)
ALIASES = {}
for _t, _n in NAMES.items():
    ALIASES[_t.lower()] = _t
    ALIASES[_t.lower().replace("-", "")] = _t
    ALIASES[_n.lower()] = _t
ALIASES.update(_EXTRA)

# 칩으로 보여줄 인기 종목
POPULAR = ["NVDA", "AAPL", "TSLA", "MSFT", "AMZN", "GOOGL", "META", "AMD"]

# 매일 아침 미리 분석해 두는 종목 (company_curate.py 와 일치)
PRECOMPUTED = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "META"]


def _norm(q):
    """비교용으로 다듬는다. 공백·점·하이픈을 떼고 소문자로."""
    return "".join(q.lower().split()).replace(".", "").replace("-", "")


def resolve(q):
    """검색어를 (티커, 한글이름, 확실한가) 로 바꾼다.

    확실한가=True  사전에 있는 종목. 바로 쓰면 된다
    확실한가=False 사전에 없지만 티커처럼 생겼다. yfinance 로 확인해야 한다
    못 찾으면 (None, None, False)
    """
    q = (q or "").strip()
    if not q:
        return None, None, False

    hit = ALIASES.get(_norm(q))
    if hit:
        return hit, NAMES.get(hit, hit), True

    # 한국 종목 코드 — '005930' 또는 '005930.KS'
    #
    # 숫자 6자리는 한국 종목 코드다. 미국 티커는 숫자로만 되어 있지 않다.
    # 접미사를 안 붙이면 야후가 못 찾으므로 .KS 를 붙여준다.
    bare = q.upper().replace(" ", "")
    if bare.endswith((".KS", ".KQ")) and bare[:-3].isdigit() and len(bare) == 9:
        return bare, NAMES.get(bare, bare), bare in NAMES
    if bare.isdigit() and len(bare) == 6:
        guess = bare + ".KS"
        return guess, NAMES.get(guess, guess), guess in NAMES

    # 사전에 없다. 티커처럼 생겼으면 후보로 넘긴다 (예: 'ADSK', 'PANW')
    #
    # ⚠️ isalnum() 은 유니코드라서 한글도 통과한다. '현대차' 가 티커 후보로
    # 잡혀서 yfinance 를 헛돌게 했다. ASCII 영문·숫자만 받는다.
    up = q.upper().replace(" ", "")
    ok = up and all(("A" <= c <= "Z") or c.isdigit() or c in ".-" for c in up)
    if ok and 1 <= len(up) <= 6:
        return up, up, False

    return None, None, False


def has_hangul(q):
    """한글이 섞여 있나. 사전에 없는 한글 검색어는 티커일 수 없으므로,
    화면에서 '미국 종목만 지원한다' 고 안내하는 데 쓴다."""
    return any("\uac00" <= c <= "\ud7a3" or "\u3131" <= c <= "\u318e" for c in (q or ""))


def name_of(ticker):
    return NAMES.get((ticker or "").upper(), (ticker or "").upper())
