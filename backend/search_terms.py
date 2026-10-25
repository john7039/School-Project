"""한국어 검색어를 영어 기사에서 찾을 수 있게 바꿔주는 사전.

수집한 기사(news)는 Finnhub·Yahoo 에서 받아오므로 제목·요약이 전부 영어다.
사용자는 한국어로 검색하므로, 그대로 LIKE 를 걸면 한 건도 안 걸린다.
그래서 한국어 검색어를 대응하는 영어 표현들로 넓혀서 함께 찾는다.

제목 한국어 번역(news.title_ko)이 채워진 기사는 사전 없이도 바로 걸리므로,
이 사전은 "번역이 아직 없는 기사까지 걸리게 하는" 보조 수단이다. 둘 다 쓴다.
"""

# 한국어 검색어 -> 기사에서 찾아볼 영어 표현들
SYNONYMS = {
    # 물가·금리
    "물가": ["inflation", "CPI", "consumer price", "prices"],
    "인플레이션": ["inflation", "CPI"],
    "금리": ["interest rate", "rates", "Fed", "Federal Reserve", "FOMC"],
    "기준금리": ["interest rate", "Fed", "FOMC", "policy rate"],
    "연준": ["Fed", "Federal Reserve", "FOMC", "Powell"],
    "금리인하": ["rate cut", "cut rates", "easing"],
    "금리인상": ["rate hike", "raise rates", "tightening"],
    # 고용·경기
    "실업": ["unemployment", "jobless", "layoff", "job cuts"],
    "고용": ["jobs", "employment", "payrolls", "hiring"],
    "경기침체": ["recession", "downturn", "slowdown"],
    "성장": ["growth", "GDP", "expansion"],
    "경제": ["economy", "economic"],
    # 시장
    "주가": ["stock", "shares", "stocks"],
    "증시": ["market", "stocks", "index", "S&P", "Nasdaq", "Dow"],
    "상승": ["rise", "gain", "surge", "jump", "rally", "higher"],
    "하락": ["fall", "drop", "decline", "slide", "plunge", "lower"],
    "실적": ["earnings", "results", "revenue", "profit"],
    "배당": ["dividend"],
    "거래량": ["volume", "trading volume"],
    "변동성": ["volatility", "VIX"],
    # 환율·원자재
    "환율": ["exchange rate", "currency", "dollar", "won", "FX"],
    "달러": ["dollar", "USD", "greenback"],
    "유로": ["euro", "EUR"],
    "엔화": ["yen", "JPY"],
    "유가": ["oil", "crude", "WTI", "Brent"],
    "금값": ["gold"],
    "비트코인": ["bitcoin", "BTC", "crypto"],
    "가상화폐": ["crypto", "bitcoin", "digital asset"],
    # 정책·사건
    "관세": ["tariff", "trade war", "duties"],
    "규제": ["regulation", "antitrust", "probe", "lawsuit"],
    "무역": ["trade", "export", "import"],
    "전쟁": ["war", "conflict", "sanctions"],
    "공급망": ["supply chain", "shortage"],
    "반도체": ["chip", "semiconductor", "AI chip"],
    "인공지능": ["AI", "artificial intelligence"],
    "전기차": ["EV", "electric vehicle"],
    # 우리가 주가를 추적하는 7개 종목
    "애플": ["Apple", "AAPL", "iPhone"],
    "마이크로소프트": ["Microsoft", "MSFT", "Azure"],
    "엔비디아": ["Nvidia", "NVDA"],
    "아마존": ["Amazon", "AMZN", "AWS"],
    "구글": ["Google", "Alphabet", "GOOGL"],
    "테슬라": ["Tesla", "TSLA", "Musk"],
    "메타": ["Meta", "Facebook", "META", "Instagram"],

    # 주가는 안 받지만 기사에는 자주 나오는 기업들.
    # 사용자가 '삼성' 을 쳤는데 0건이 나와서 넣었다 — 삼성 기사는 19건이나
    # 있었고, 사전에 한국어 이름이 없어서 못 찾았던 것뿐이다.
    #
    # 넣을지 말지는 실제 기사 수로 정했다(5건 이상). 기사가 없는 이름을
    # 넣으면 눌러도 0건이라 없느니만 못하다. 현대차·기아·닌텐도는 기사가
    # 0건이라 뺐다 — Finnhub 수집이 위 7종목과 일반 경제 중심이라 그렇다.
    #
    # 티커는 영어 단어와 겹치지 않는 것만 쓴다. COST(코스트코)를 넣었더니
    # 본문의 'cost'에 걸려 7건짜리가 75건으로 부풀었다. KO·MU·BA·DIS·
    # CRM·HOOD·ARM 도 같은 이유로 뺐다.
    "삼성": ["Samsung"],
    "SK하이닉스": ["SK Hynix", "Hynix"],
    "TSMC": ["TSMC", "Taiwan Semiconductor"],
    "인텔": ["Intel", "INTC"],
    "AMD": ["AMD"],
    "브로드컴": ["Broadcom", "AVGO"],
    "퀄컴": ["Qualcomm", "QCOM"],
    "마이크론": ["Micron"],
    "넷플릭스": ["Netflix", "NFLX"],
    "디즈니": ["Disney"],
    "우버": ["Uber"],
    "스타벅스": ["Starbucks", "SBUX"],
    "맥도날드": ["McDonald"],
    "나이키": ["Nike"],
    "코카콜라": ["Coca-Cola", "Coca Cola"],
    "월마트": ["Walmart", "WMT"],
    "코스트코": ["Costco"],
    "보잉": ["Boeing"],
    "포드": ["Ford"],
    "GM": ["General Motors"],
    "제이피모건": ["JPMorgan"],
    "골드만삭스": ["Goldman Sachs"],
    "버크셔": ["Berkshire"],
    "비자": ["Visa"],
    "마스터카드": ["Mastercard"],
    "팔란티어": ["Palantir", "PLTR"],
    "오라클": ["Oracle", "ORCL"],
    "세일즈포스": ["Salesforce"],
    "어도비": ["Adobe", "ADBE"],
    "IBM": ["IBM"],
    "시스코": ["Cisco", "CSCO"],
    "델컴퓨터": ["Dell"],          # '델' 로 두면 '모델' 에 걸린다
    "알리바바": ["Alibaba", "BABA"],
    "스페이스X": ["SpaceX"],
    "오픈AI": ["OpenAI"],
    "앤트로픽": ["Anthropic"],
    "리비안": ["Rivian", "RIVN"],
    "루시드": ["Lucid"],
    "로빈후드": ["Robinhood"],
}


# 기사가 없는 단어를 쳤을 때 "대신 이런 건 있어요" 로 보여줄 것들.
# 빈 화면만 돌려주면 사용자는 서비스가 고장 난 줄 안다.
POPULAR = ["엔비디아", "테슬라", "반도체", "인공지능", "금리",
           "실적", "넷플릭스", "삼성", "환율", "물가"]


def expand(query):
    """검색어를 실제로 찾아볼 표현 목록으로 넓힌다.

    원본은 항상 1순위로 남긴다 — 영어로 검색했거나 title_ko 가 채워진
    기사는 원본 그대로가 제일 정확하게 걸리기 때문.
    """
    q = (query or "").strip()
    if not q:
        return []
    terms = [q]
    for ko, en_list in SYNONYMS.items():
        # "금리인하" 처럼 검색어가 사전 표제어를 품고 있어도 걸리게
        if ko in q:
            for en in en_list:
                if en.lower() not in (t.lower() for t in terms):
                    terms.append(en)
    return terms
