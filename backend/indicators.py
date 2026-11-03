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
        "about": "물건과 서비스 값을 한 바구니에 담아 매달 재는 숫자다. "
                 "그 바구니 값이 작년 같은 달보다 얼마나 비싸졌는지가 '물가' 다.",
        "drivers": "유가 · 환율 · 임금 · 집세 · 식료품 값",
        "affects": "기준금리 결정 · 월급의 실제 가치 · 채권 금리",
        "source": "미국 노동통계국(BLS). 매달 중순에 전달 수치를 낸다",
        "caveat": "연준의 물가 목표는 2% 다. 다만 연준이 실제로 보는 건 PCE 라는 "
                  "다른 지표라서, CPI 와는 조금 어긋난다. 그래서 이 그래프에 "
                  "2% 선을 긋지 않았다.",
    },
    "금리": {
        "label": "기준금리",
        "unit": "percent",
        "decimals": 2,
        "about": "은행끼리 하루 동안 돈을 빌릴 때 매기는 값이다. "
                 "모든 대출 금리가 여기서부터 쌓여 올라간다.",
        "drivers": "물가와 고용. 연준이 이 둘을 보고 정한다",
        "affects": "대출·카드 이자 · 주가 · 환율 · 집값",
        "source": "연준(Fed). 1년에 여덟 번 모여 정한다",
        "caveat": "이 숫자는 연준이 정한 '목표 범위' 가 아니라, 그 범위 안에서 "
                  "실제로 거래된 금리의 월평균이다. 그래서 3.75% 처럼 딱 떨어지지 "
                  "않고 3.88% 같은 값이 나온다.",
    },
    "실업률": {
        "label": "실업률",
        "unit": "percent",
        "decimals": 1,
        "about": "일할 생각이 있는 사람 중 일자리를 못 구한 사람의 비율이다. "
                 "구직을 아예 포기한 사람은 이 계산에 들어가지 않는다.",
        "drivers": "경기 · 기업의 채용과 해고",
        "affects": "임금 → 물가 → 금리. 소비 여력",
        "source": "미국 노동통계국(BLS). 보통 매달 첫 금요일",
        "caveat": "낮을수록 좋기만 한 것은 아니다. 너무 낮으면 사람을 구하려고 "
                  "임금을 올리게 되고, 그게 물가를 밀어올려 금리 인상 쪽으로 간다.",
    },
}

# 세 지표가 왜 같은 탭에 있나 — 따로 보면 숫자 세 개지만 고리로 보면 이야기가 된다.
# 교과서에 나오는 고리이고, 실제로 이 순서대로 돌지 않는 때도 많다(그래서 '보통').
CHAIN = [
    "물가가 오른다",
    "연준이 금리를 올린다",
    "돈 빌리기가 비싸진다",
    "기업이 덜 뽑는다",
    "실업률이 오른다",
    "임금 상승이 멈춘다",
    "물가가 내린다",
]

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

        out.append({
            "name": name,
            "label": spec["label"],
            "about": spec["about"],
            "drivers": spec.get("drivers"),
            "affects": spec.get("affects"),
            "source": spec.get("source"),
            "caveat": spec.get("caveat"),
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
