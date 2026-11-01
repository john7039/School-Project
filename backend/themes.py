"""테마(업종) 사전 — "유가", "반도체" 처럼 회사가 아닌 말로 종목을 찾는다.

사전이 세 번째다. 앞의 둘과 같은 방식이라 새 구조가 아니다.
  search_terms.py   한국어 → 영어 표현     (기사 검색)
  tickers.py        이름 → 티커            (종목 검색)
  themes.py         테마 → 티커 묶음       (여기)

왜 필요한가 — 종목 검색에 "유가" 를 치면 영원히 0건이다. 유가는 외국 주식이
아니라 회사가 아니기 때문이다. 그런데 사용자가 알고 싶은 것은 분명하다:
유가가 지금 얼마고, 관련 기업들이 어떻게 움직였나.

각 테마에 '대표 지표' 를 하나 둔다. "유가" 를 검색한 사람이 정작 보고 싶은
것은 유가 자체(CL=F)다. 관련 기업만 보여주면 질문에 답한 것이 아니다.
"""

THEMES = {
    "반도체": {
        "short": "반도체",
        "name": "반도체",
        "tickers": ["NVDA", "AMD", "TSM", "AVGO", "QCOM",
                    "MU", "INTC", "ARM", "ASML", "AMAT"],
        "index": ("SOXX", "반도체 ETF"),
        "aliases": ["반도체", "칩", "메모리", "semiconductor", "chip", "chips",
                    "파운드리", "gpu"],
    },
    "유가": {
        "short": "유가",
        "name": "유가 · 에너지",
        "tickers": ["XOM", "CVX", "SHEL", "BP", "TTE",
                    "EQNR", "PBR", "COP", "OXY", "SLB"],
        "index": ("CL=F", "WTI 유가"),
        "aliases": ["유가", "석유", "원유", "정유", "에너지", "oil", "crude",
                    "wti", "brent", "기름"],
    },
    "자동차": {
        "short": "자동차",
        "name": "자동차 · 전기차",
        "tickers": ["TSLA", "TM", "F", "GM", "HMC", "STLA", "RIVN", "LCID", "NIO"],
        "index": None,
        "aliases": ["자동차", "전기차", "완성차", "ev", "car", "auto", "배터리차"],
    },
    "빅테크": {
        "short": "빅테크",
        "name": "빅테크",
        "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
        "index": ("QQQ", "나스닥100 ETF"),
        "aliases": ["빅테크", "기술주", "테크", "it", "bigtech", "플랫폼",
                    "매그니피센트", "m7", "매그니피센트7", "마그니피센트"],
    },
    "금융": {
        "short": "금융",
        "name": "금융 · 은행",
        "tickers": ["JPM", "BAC", "WFC", "C", "GS", "MS", "V", "MA", "AXP", "BLK"],
        "index": ("^TNX", "미 10년물 금리"),
        "aliases": ["금융", "은행", "카드", "금융주", "bank", "증권"],
    },
    "소비": {
        "short": "소비",
        "name": "소비 · 유통",
        "tickers": ["WMT", "COST", "HD", "TGT", "MCD",
                    "SBUX", "KO", "PEP", "PG", "NKE"],
        "index": None,
        "aliases": ["소비", "유통", "소비재", "소매", "retail", "먹거리", "식품"],
    },
    "헬스케어": {
        "short": "헬스케어",
        "name": "헬스케어 · 제약",
        "tickers": ["LLY", "JNJ", "MRK", "ABBV", "PFE",
                    "AMGN", "BMY", "UNH", "TMO", "NVO"],
        "index": None,
        "aliases": ["헬스케어", "제약", "바이오", "의료", "pharma", "health",
                    "백신", "신약"],
    },
    "항공방산": {
        "short": "방산",
        "name": "항공 · 방산",
        "tickers": ["BA", "LMT", "RTX", "NOC", "GD", "LHX", "HII"],
        "index": None,
        "aliases": ["항공", "방산", "우주", "defense", "무기", "비행기"],
    },
    "소프트웨어": {
        "short": "소프트웨어",
        "name": "소프트웨어 · 플랫폼",
        "tickers": ["ORCL", "CRM", "ADBE", "PLTR", "SNOW",
                    "NFLX", "UBER", "ABNB", "SHOP", "COIN"],
        "index": None,
        "aliases": ["소프트웨어", "플랫폼", "클라우드", "saas", "software",
                    "구독", "앱"],
    },
    "지수": {
        "short": "지수",
        "name": "미국 지수",
        "tickers": ["SPY", "QQQ", "DIA", "IWM", "VTI"],
        "index": ("^GSPC", "S&P500 지수"),
        # 나스닥·다우·s&p 는 tickers.py 가 QQQ·DIA·SPY 로 먼저 받는다.
        # 종목이 테마보다 구체적이라 그쪽이 이기는 게 맞고, 여기 남겨두면
        # 영원히 닿지 않는 죽은 별칭이 된다.
        "aliases": ["지수", "미국지수", "미국시장", "index", "삼대지수"],
    },
}

# ── 한국 상장 ─────────────────────────────────────────
#
# 미국 업종과 섞지 않는다. 한 목록에 "엔비디아 204.64" 와 "삼성전자 225,000"
# 이 나란히 있으면 단위를 적어도 비교가 안 되고, 평균 등락률 말고는 읽을 게
# 없어진다. 시장을 나눠 두면 각 목록 안에서 비교가 된다.
KOREA = {
    "한국대형주": {
        "short": "한국 대형주",
        "name": "한국 대형주",
        "tickers": ["005930.KS", "000660.KS", "373220.KS", "207940.KS",
                    "005380.KS", "035420.KS", "000270.KS", "005490.KS",
                    "012330.KS", "066570.KS"],
        "index": ("^KS11", "코스피"),
        "aliases": ["한국대형주", "코스피대형주", "한국주식", "국내주식",
                    "한국", "국내", "시가총액"],
    },
    "한국반도체": {
        "short": "한국 반도체",
        "name": "한국 반도체 · 배터리",
        "tickers": ["005930.KS", "000660.KS", "373220.KS", "006400.KS",
                    "051910.KS"],
        "index": None,
        "aliases": ["한국반도체", "국내반도체", "배터리", "이차전지", "2차전지",
                    "셀메이커"],
    },
    "한국자동차": {
        "short": "한국 자동차",
        "name": "한국 자동차",
        "tickers": ["005380.KS", "000270.KS", "012330.KS"],
        "index": None,
        "aliases": ["한국자동차", "국내자동차", "현대차그룹", "완성차국내"],
    },
    "한국금융": {
        "short": "한국 금융",
        "name": "한국 금융",
        "tickers": ["105560.KS", "055550.KS", "086790.KS"],
        "index": None,
        "aliases": ["한국금융", "국내금융", "은행주", "금융지주"],
    },
    "한국조선방산": {
        "short": "조선 · 방산",
        "name": "한국 조선 · 방산",
        "tickers": ["009540.KS", "042660.KS", "012450.KS"],
        "index": None,
        "aliases": ["조선", "조선주", "한국방산", "국내방산", "k방산", "방산주"],
    },
    "한국인터넷": {
        "short": "한국 인터넷",
        "name": "한국 인터넷 · 통신",
        "tickers": ["035420.KS", "035720.KS", "017670.KS", "030200.KS",
                    "032640.KS"],
        "index": None,
        "aliases": ["한국인터넷", "국내인터넷", "통신", "통신주", "플랫폼국내"],
    },
}
THEMES.update(KOREA)

# 칩에 보여줄 순서 — 미국 먼저, 그다음 한국. 칩에서도 시장이 섞이지 않게 묶는다.
US_ORDER = ["반도체", "빅테크", "소프트웨어", "유가", "자동차", "금융", "소비",
            "헬스케어", "항공방산", "지수"]
KR_ORDER = ["한국대형주", "한국반도체", "한국자동차", "한국금융",
            "한국조선방산", "한국인터넷"]
ORDER = US_ORDER + KR_ORDER

_ALIAS = {}
for _k, _v in THEMES.items():
    for _a in _v["aliases"] + [_k, _v["name"]]:
        _ALIAS["".join(_a.lower().split())] = _k


def resolve(q):
    """검색어를 테마 키로. 못 찾으면 None."""
    q = (q or "").strip()
    if not q:
        return None
    return _ALIAS.get("".join(q.lower().split()))


def get(key):
    return THEMES.get(key)


def chips():
    """화면에 뿌릴 칩 목록.

    칩에는 짧은 이름(short)을 쓴다. "유가 · 에너지" 를 칩에 그대로 쓰면
    칩이 여러 개 나란히 있을 때 가운뎃점이 칩 사이 구분처럼 보여서
    "유가 · 에너지 · 자동차 · 전기차" 가 넷으로 읽힌다.
    """
    return [{"key": k, "short": THEMES[k]["short"], "name": THEMES[k]["name"],
             "count": len(THEMES[k]["tickers"]),
             "market": "한국" if k in KR_ORDER else "미국"}
            for k in ORDER if k in THEMES]


def all_symbols(key):
    """시세를 받아올 심볼 전부 — 종목 + 대표 지표."""
    t = THEMES.get(key)
    if not t:
        return []
    syms = list(t["tickers"])
    if t.get("index"):
        syms.append(t["index"][0])
    return syms
