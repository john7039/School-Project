"""경제지표를 사람이 읽는 숫자로 바꾼다.

화면에 `CPI 336.298` 이 떠 있었다. 1982~84년 평균을 100 으로 놓은 지수라
그 숫자 자체로는 아무 뜻이 없다. 뉴스가 말하는 '물가' 는 전년 동월 대비
상승률이고, 그건 우리가 이미 가진 44개월로 계산할 수 있다.

⚠️ **셋에 같은 계산을 쓰면 틀린다 — 단위가 다르다.**

    CPI      지수다      비율(%) 로 읽는다     324.245 → 336.298 = +3.7%
    수출·수입  금액이다     비율(%) 로 읽는다     982.8억 달러 자체는 비교 기준이 없다
    금리      이미 % 다   차이(%p) 로 읽는다    4.09% → 3.88% = -0.21%p
    실업률    이미 % 다   차이(%p) 로 읽는다    4.4% → 4.2% = -0.20%p

  "금리가 작년보다 5.13% 내렸다" 는 틀린 문장이다. 4.09% 에서 3.88% 로
  내린 것이니 **0.21%p** 다. 뉴스도 "기준금리 0.25%p 인하" 라고 쓴다.
  달러를 '원' 으로 쓴 것, 거래일을 KST 로 자른 것과 같은 종류의 사고다.
  그래서 단위를 데이터 옆에(SPEC) 적어두고 계산을 여기 한 곳에 모았다.

AI 는 쓰지 않는다. 지표가 **왜** 움직였는지는 우리 데이터에 없어서 물어보면
지어낸다(업종 판단을 계산으로 낸 것과 같은 이유). 대신 센 것만 말한다 —
몇 달 연속 올랐나.
"""

# 키가 (나라, 이름) 이다. 테이블에도 country 컬럼이 있고 UNIQUE 가
# (country, name, date) 라서, 한국 CPI 를 넣어도 미국 것과 안 부딪힌다.
# (2026-11-06 마이그레이션. 그전에는 SPEC 만 나라를 알고 있었다.)
SPEC = {
    ("US", "CPI"): {
        "label": "물가 (CPI)",
        "unit": "index",
        "decimals": 1,          # 화면에 보이는 상승률 자릿수
        "raw_decimals": 3,      # 지수 원값 자릿수
        "tip": {
            "term": "Consumer Price Index · 소비자물가지수",
            "what": "우리가 매달 사 먹고 쓰는 물건 값을 한 바구니에 담아, "
                    "그 바구니가 작년보다 얼마나 비싸졌는지 잰다",
            "effect": "오르면 같은 월급으로 살 수 있는 게 줄어든다",
        },
        # ⚠️ 교과서에 나오는 '보통 이렇게 작용한다' 다. 지금 데이터에 대한
        #    주장이 아니다. 그래서 화면에도 "오르면 보통" 이라고 적는다.
        "impact": [
            ("🛒", "일상", "장바구니·외식비가 오른다"),
            ("📉", "주식", "금리 인상 우려로 부담"),
            ("🏦", "예적금", "이자를 받아도 실제 가치는 줄어든다"),
        ],
        "tags": {
            1: "🚨 장바구니가 계속 비싸지고 있어요",
            0: "➖ 물가 오름세가 제자리예요",
            -1: "🧊 물가 오름세가 꺾였어요",
        },
    },
    ("US", "금리"): {
        "label": "기준금리",
        "unit": "percent",
        "decimals": 2,
        "tip": {
            "term": "Federal Funds Rate · 미국 기준금리",
            "what": "은행끼리 하루 돈을 빌릴 때의 값. 모든 대출과 예금 금리가 "
                    "여기서부터 쌓여 올라간다",
            "effect": "오르면 대출 이자가 늘고, 주식에서 예금으로 돈이 옮겨간다",
        },
        "impact": [
            ("🏦", "예적금", "받는 이자가 늘어난다"),
            ("🏠", "대출", "갚을 이자가 늘어난다"),
            ("📉", "주식", "돈이 예금으로 빠져 부담"),
        ],
        "tags": {
            1: "💰 대출 이자가 오르는 쪽이에요",
            0: "➖ 금리가 멈춰 있어요",
            -1: "💸 대출 이자가 내리는 쪽이에요",
        },
    },
    ("US", "실업률"): {
        "label": "실업률",
        "unit": "percent",
        "decimals": 1,
        "tip": {
            "term": "Unemployment Rate · 실업률",
            "what": "일할 생각이 있는 사람 100명 중 몇 명이 일자리를 못 구했는지. "
                    "구직을 아예 포기한 사람은 여기 들어가지 않는다",
            "effect": "오르면 소비가 줄고, 연준이 금리를 내릴 쪽으로 기운다",
        },
        "impact": [
            ("🧑‍💼", "일자리", "채용이 줄고 이직이 어려워진다"),
            ("🛒", "소비", "지갑을 닫아 경기가 식는다"),
            ("💸", "금리", "연준이 내릴 쪽으로 기운다"),
        ],
        "tags": {
            1: "🧑‍💼 일자리 구하기가 어려워지고 있어요",
            0: "➖ 고용 사정이 비슷해요",
            -1: "🙌 일자리 사정이 나아지고 있어요",
        },
    },
    ("KR", "CPI"): {
        "label": "물가 (CPI)",
        "unit": "index",
        "decimals": 1,
        "raw_decimals": 3,
        # 기준연도가 미국과 다르다 (한국 2020=100, 미국 1982~84=100).
        # 상승률로 바꿔 쓰니 상관없다 — 지수 값끼리 비교하지만 않으면 된다.
        "tip": {
            "term": "소비자물가지수 · 통계청",
            "what": "우리가 매달 사 먹고 쓰는 물건 값을 한 바구니에 담아, "
                    "그 바구니가 작년보다 얼마나 비싸졌는지 잰다",
            "effect": "오르면 같은 월급으로 살 수 있는 게 줄어든다",
        },
        "impact": [
            ("🛒", "일상", "장바구니·외식비가 오른다"),
            ("🏦", "금리", "한국은행이 금리를 올릴 쪽으로 기운다"),
            ("💵", "환율", "수입 물가가 오르면 더 밀려 올라간다"),
        ],
        "tags": {
            1: "🚨 장바구니가 계속 비싸지고 있어요",
            0: "➖ 물가 오름세가 제자리예요",
            -1: "🧊 물가 오름세가 꺾였어요",
        },
    },
    ("KR", "금리"): {
        "label": "콜금리",
        "unit": "percent",
        "decimals": 2,
        # ⚠️ 한국은행 기준금리가 아니다. 기준금리는 ECOS 에만 있다.
        #    콜금리는 한국은행이 기준금리에 맞춰 유도하는 시장금리라 가깝게
        #    움직이지만 같은 수치는 아니다. 화면에도 그렇게 쓴다.
        "tip": {
            "term": "콜금리 · 은행 간 하루 금리",
            "what": "은행끼리 하루 돈을 빌릴 때의 값. 한국은행 기준금리를 따라 "
                    "움직이지만 같은 수치는 아니다",
            "effect": "오르면 대출 이자가 늘고, 주식에서 예금으로 돈이 옮겨간다",
        },
        "impact": [
            ("🏦", "예적금", "받는 이자가 늘어난다"),
            ("🏠", "대출", "갚을 이자가 늘어난다"),
            ("💵", "환율", "미국 금리와의 차이가 좁아지면 원화에 힘이 된다"),
        ],
        "tags": {
            1: "💰 대출 이자가 오르는 쪽이에요",
            0: "➖ 금리가 멈춰 있어요",
            -1: "💸 대출 이자가 내리는 쪽이에요",
        },
    },
    ("KR", "수출"): {
        "label": "수출",
        "unit": "amount",
        "decimals": 1,
        "raw_decimals": 1,
        "raw_div": 1e8,        # 달러 → 억 달러
        "raw_unit": "억 달러",
        # ⚠️ 계절 조정을 안 한 시리즈다 (OECD ADJUSTMENT: N). 2월이 짧고 설
        #    연휴가 있어서 **3월은 해마다 크게 뛴다** — 2010년 이후 전월 대비
        #    상위 10개 중 여섯이 3월이다. 전월과 비교하면 숫자가 거짓말을 한다.
        #    작년 같은 달과만 견준다. (CPI·실업률은 조정된 시리즈라 괜찮다)
        "mom": False,
        "tip": {
            "term": "Exports of Goods · 상품 수출액",
            "what": "한 달 동안 한국이 외국에 물건을 팔아 번 돈. "
                    "금액만으로는 비교 기준이 없어서 작년 같은 달과 견준다",
            "effect": "늘면 기업 실적과 일자리에 좋고, 달러가 들어와 환율이 내리는 쪽",
        },
        "impact": [
            ("🏭", "기업", "반도체·자동차 실적이 좋아진다"),
            ("💵", "환율", "달러가 들어와 원화가 강해지는 쪽"),
            ("📈", "주식", "수출주 실적 기대가 커진다"),
        ],
        "tags": {
            1: "📦 수출이 작년보다 늘고 있어요",
            0: "➖ 수출이 작년과 비슷해요",
            -1: "📦 수출이 작년보다 줄고 있어요",
        },
    },
    ("KR", "수입"): {
        "label": "수입",
        "unit": "amount",
        "decimals": 1,
        "raw_decimals": 1,
        "raw_div": 1e8,
        "raw_unit": "억 달러",
        "mom": False,
        "tip": {
            "term": "Imports of Goods · 상품 수입액",
            "what": "한 달 동안 한국이 외국에서 물건을 사 온 돈. "
                    "원유·가스·원자재가 큰 몫을 차지한다",
            "effect": "늘면 원가와 물가에 부담이고, 달러가 나가 환율이 오르는 쪽",
        },
        "impact": [
            ("🛒", "물가", "원자재·에너지 값이 물가로 넘어온다"),
            ("💵", "환율", "달러가 나가 원화가 약해지는 쪽"),
            ("🏭", "기업", "원가 부담이 커진다"),
        ],
        "tags": {
            1: "🚢 수입이 작년보다 늘고 있어요",
            0: "➖ 수입이 작년과 비슷해요",
            -1: "🚢 수입이 작년보다 줄고 있어요",
        },
    },
}

# 3년 범위를 셋으로 가르는 경계. ⚠️ 1/3·2/3 은 내가 고른 값이다.
# 다만 '안정·주의·경고' 같은 판단이 아니라 **관측된 범위 안의 위치**라서,
# "왜 하필 이 선인가" 에 "지난 3년을 삼등분했다" 고 답할 수 있다.
# 연준 목표 2% 를 기준으로 쓰지 않은 이유 — 그 목표는 CPI 가 아니라 PCE 기준이다.
BAND_LOW, BAND_HIGH = 1 / 3, 2 / 3

# 화면에 놓을 순서. 나라로 묶고, 미국은 물가 → 그 때문에 움직이는 금리 → 일자리.
# 한국은 수출로 먹고 사는 나라라 수출·수입을 둔다.
# 원/달러 환율은 여기 넣지 않는다 — 환율 탭이 장중 그래프·해설까지 이미 다 한다.
# (아침에 종목별 탭이 생겨 시장·지표 탭의 주가 카드를 걷어낸 것과 같은 이유다.)
ORDER = [("US", "CPI"), ("US", "금리"), ("US", "실업률"),
         ("KR", "CPI"), ("KR", "금리"), ("KR", "수출"), ("KR", "수입")]


def _month_label(date):
    """'2026-09-01' → '2026년 9월분'. date 는 기준월이지 발표일이 아니다."""
    return f"{date[:4]}년 {int(date[5:7])}월분"


def _release_label(rel):
    if not rel:
        return None
    _, mm, dd = rel.split("-")
    return f"{int(mm)}/{int(dd)} 발표"


def _tick(date):
    """그래프 x축 라벨. '2026-09-01' → '26.09'"""
    return f"{date[2:4]}.{date[5:7]}"


def _yoy_series(pairs):
    """[(date, value)] → [(date, 전년 대비 상승률 %)].

    12개월 전이 있는 달만 나온다. 2023-01 부터 모았으니 2024-01 부터다.
    """
    by = dict(pairs)
    out = []
    for date, v in pairs:
        prev = by.get(f"{int(date[:4]) - 1}{date[4:]}")
        if prev:
            out.append((date, (v / prev - 1) * 100))
    return out


def _streak(vals, decimals):
    """마지막 걸음과 같은 방향이 몇 달 이어졌나 → (방향, 개월).

    **화면에 같은 숫자로 보이면 보합으로 센다.** 3.634 와 3.635 의 차이를
    "올랐다" 고 말하면 거짓말에 가깝다. 비교를 표시 자릿수로 맞추면
    말과 숫자가 어긋나지 않는다.
    """
    r = [round(v, decimals) for v in vals]
    if len(r) < 2:
        return 0, 0

    def step(a, b):
        return 0 if b == a else (1 if b > a else -1)

    s = step(r[-2], r[-1])
    n, i = 1, len(r) - 2
    while i >= 1 and step(r[i - 1], r[i]) == s:
        n += 1
        i -= 1
    return s, n


# 태그를 무엇으로 고를까.
#   percent·index  추세 방향. 금리가 오르는 중인가, 물가 오름세가 꺾였나
#   amount         머리 숫자의 부호. "작년보다 늘었나 줄었나" 가 먼저 궁금하다
#
# ⚠️ 이걸 안 나눠서 버그가 났다. 수입이 +22.4%(작년보다 늘었다) 인데 증감률이
#    낮아지는 중이라 추세 방향이 -1 이었고, 태그가 "수입이 작년보다 줄고
#    있어요" 로 나왔다. 숫자와 글이 정면으로 어긋났다.
def _tag_key(spec, direction, headline):
    if spec["unit"] == "amount":
        if headline is None:
            return 0
        return 1 if headline > 0 else (-1 if headline < 0 else 0)
    return direction


def _note(name, direction, months):
    """센 것만 말한다. 왜 움직였는지는 모르니 쓰지 않는다."""
    if not months:
        return ""
    if name in ("수출", "수입"):
        if direction == 0:
            return f"작년 대비 증감률이 {months}개월째 비슷합니다."
        word = "높아지고" if direction > 0 else "낮아지고"
        if months == 1:
            return f"작년 대비 증감률이 지난달보다 {'높아졌' if direction > 0 else '낮아졌'}습니다."
        return f"작년 대비 증감률이 {months}개월 연속 {word} 있습니다."
    if name == "CPI":
        if direction == 0:
            return f"상승률이 {months}개월째 같은 수준입니다."
        if months == 1:
            return f"상승률이 지난달보다 {'높아졌' if direction > 0 else '낮아졌'}습니다."
        return f"상승률이 {months}개월 연속 {'높아지고' if direction > 0 else '낮아지고'} 있습니다."
    if direction == 0:
        return f"{months}개월째 그대로입니다."
    word = "올랐" if direction > 0 else "내렸"
    if months == 1:
        return f"지난달보다 {word}습니다."
    return f"{months}개월 연속 {word}습니다."


def _amount(value, unit, decimals):
    return None if value is None else {
        "value": round(value, decimals), "unit": unit, "decimals": decimals,
    }


def build(conn):
    """화면이 그대로 그릴 수 있는 지표 목록."""
    rows = conn.execute(
        "SELECT country, name, date, value, release_date FROM indicators ORDER BY date"
    ).fetchall()

    by_key = {}
    for r in rows:
        by_key.setdefault((r["country"], r["name"]), []).append(
            (r["date"], r["value"], r["release_date"]))

    out = []
    for key in ORDER:
        series = by_key.get(key)
        if not series:
            continue
        country, name = key
        spec = SPEC[key]
        dec = spec["decimals"]
        pairs = [(d, v) for d, v, _ in series]
        date, value, release = series[-1]
        prev_month = pairs[-2][1] if len(pairs) >= 2 else None
        same_month_last_year = dict(pairs).get(f"{int(date[:4]) - 1}{date[4:]}")

        if spec["unit"] in ("index", "amount"):
            # 지수는 거의 단조증가라 선을 그려도 읽을 게 없다. 그래프도 상승률로.
            chart_pairs = _yoy_series(pairs)
            headline = chart_pairs[-1][1] if chart_pairs else None
            yoy = _amount(headline, "%", dec)
            mom = _amount(
                (value / prev_month - 1) * 100 if prev_month else None, "%", dec)
            if not spec.get("mom", True):
                mom = None
        else:
            chart_pairs = pairs
            headline = value
            yoy = _amount(
                value - same_month_last_year if same_month_last_year is not None else None,
                "%p", dec)
            mom = _amount(
                value - prev_month if prev_month is not None else None, "%p", dec)

        direction, months = _streak([v for _, v in chart_pairs], dec)

        # 숫자 하나만 보면 높은지 낮은지 알 수가 없다. 관측 범위를 옆에 놓는다.
        cvals = [v for _, v in chart_pairs]
        rlo, rhi = (min(cvals), max(cvals)) if cvals else (None, None)
        pos = (headline - rlo) / (rhi - rlo) if cvals and rhi > rlo else None
        band = None if pos is None else (
            "low" if pos < BAND_LOW else ("high" if pos >= BAND_HIGH else "mid"))

        out.append({
            "name": name,
            "label": spec["label"],
            "unit": spec["unit"],
            "date": date,
            "month": _month_label(date),
            "released": _release_label(release),
            # 계산한 숫자만 보여주면 틀렸을 때 알 수가 없다. 원값을 남긴다.
            "country": country,
            "raw": round(value / spec.get("raw_div", 1), spec.get("raw_decimals", dec)),
            "raw_decimals": spec.get("raw_decimals", dec),
            "raw_unit": spec.get("raw_unit", ""),
            "raw_name": "지수" if spec["unit"] == "index" else "",
            "headline": _amount(headline, "%", dec),
            "yoy": yoy,
            "mom": mom,
            "note": _note(name, direction, months),
            "tag": spec["tags"].get(_tag_key(spec, direction, headline)),
            "tip": spec["tip"],
            "impact": [{"icon": i, "where": w, "text": t} for i, w, t in spec["impact"]],
            # 색은 높낮이만 나타낸다. 좋고 나쁨이 아니다 — 금리가 낮은 게 좋은지는
            # 대출자냐 예금자냐에 따라 다르다. 화면에도 그렇게 적는다.
            "band": None if band is None else {
                "level": band, "pos": round(pos, 3),
                "lo": round(rlo, dec), "hi": round(rhi, dec),
                "years": round(len(cvals) / 12, 1),
            },
            "chart": {
                "unit": "%",
                "decimals": dec,
                "from": chart_pairs[0][0][:7] if chart_pairs else None,
                "to": chart_pairs[-1][0][:7] if chart_pairs else None,
                "points": [{"t": _tick(d), "rate": round(v, dec + 2)}
                           for d, v in chart_pairs],
            },
        })
    return out
