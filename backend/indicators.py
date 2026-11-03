"""경제지표를 사람이 읽는 숫자로 바꾼다.

화면에 `CPI 336.298` 이 떠 있었다. 1982~84년 평균을 100 으로 놓은 지수라
그 숫자 자체로는 아무 뜻이 없다. 뉴스가 말하는 '물가' 는 전년 동월 대비
상승률이고, 그건 우리가 이미 가진 44개월로 계산할 수 있다.

⚠️ **셋에 같은 계산을 쓰면 틀린다 — 단위가 다르다.**

    CPI      지수다      비율(%) 로 읽는다     324.245 → 336.298 = +3.7%
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

SPEC = {
    "CPI": {
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
    "금리": {
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
    "실업률": {
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
}

# 3년 범위를 셋으로 가르는 경계. ⚠️ 1/3·2/3 은 내가 고른 값이다.
# 다만 '안정·주의·경고' 같은 판단이 아니라 **관측된 범위 안의 위치**라서,
# "왜 하필 이 선인가" 에 "지난 3년을 삼등분했다" 고 답할 수 있다.
# 연준 목표 2% 를 기준으로 쓰지 않은 이유 — 그 목표는 CPI 가 아니라 PCE 기준이다.
BAND_LOW, BAND_HIGH = 1 / 3, 2 / 3

# 화면에 놓을 순서 — 물가, 그 때문에 움직이는 금리, 그리고 일자리
ORDER = ["CPI", "금리", "실업률"]


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


def _note(name, direction, months):
    """센 것만 말한다. 왜 움직였는지는 모르니 쓰지 않는다."""
    if not months:
        return ""
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
        "SELECT name, date, value, release_date FROM indicators ORDER BY date"
    ).fetchall()

    by_name = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append((r["date"], r["value"], r["release_date"]))

    out = []
    for name in ORDER:
        series = by_name.get(name)
        if not series:
            continue
        spec = SPEC[name]
        dec = spec["decimals"]
        pairs = [(d, v) for d, v, _ in series]
        date, value, release = series[-1]
        prev_month = pairs[-2][1] if len(pairs) >= 2 else None
        same_month_last_year = dict(pairs).get(f"{int(date[:4]) - 1}{date[4:]}")

        if spec["unit"] == "index":
            # 지수는 거의 단조증가라 선을 그려도 읽을 게 없다. 그래프도 상승률로.
            chart_pairs = _yoy_series(pairs)
            headline = chart_pairs[-1][1] if chart_pairs else None
            yoy = _amount(headline, "%", dec)
            mom = _amount(
                (value / prev_month - 1) * 100 if prev_month else None, "%", dec)
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
            "raw": round(value, spec.get("raw_decimals", dec)),
            "raw_decimals": spec.get("raw_decimals", dec),
            "headline": _amount(headline, "%", dec),
            "yoy": yoy,
            "mom": mom,
            "note": _note(name, direction, months),
            "tag": spec["tags"].get(direction),
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
