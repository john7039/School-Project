"""한국어 조사 붙이기.

"인텔는 업종 평균보다…" 라고 쓴 적이 있다. 받침이 있으면 '은', 없으면 '는'
인데 코드가 하나만 쓴 것이다. 화면 글자가 이러면 기계가 쓴 티가 바로 난다.

영문 티커도 받는다 — 읽는 소리로 판단한다.
  AMD(에이엠디) → 디, 받침 없음 → "AMD는"
  ASML(에이에스엠엘) → 엘, 받침 ㄹ → "ASML은"
"""

# 영문자를 한국어로 읽을 때 받침으로 끝나는 것들
#   F 에프(ㅍ) · L 엘(ㄹ) · M 엠(ㅁ) · N 엔(ㄴ) · R 아르(ㄹ) · S 에스(ㅅ) · X 엑스(ㅅ)
_CONSONANT_LETTERS = set("FLMNRSX")
# 숫자: 0 영(ㅇ) 1 일(ㄹ) 3 삼(ㅁ) 6 육(ㄱ) 7 칠(ㄹ) 8 팔(ㄹ) → 받침 있음
_CONSONANT_DIGITS = set("013678")

RIEUL = 8          # 한글 종성에서 ㄹ 의 인덱스

PAIRS = {
    "은": ("은", "는"), "는": ("은", "는"),
    "이": ("이", "가"), "가": ("이", "가"),
    "을": ("을", "를"), "를": ("을", "를"),
    "과": ("과", "와"), "와": ("과", "와"),
    "으로": ("으로", "로"), "로": ("으로", "로"),
    "이라": ("이라", "라"), "라": ("이라", "라"),
}


def has_final(word, rieul_counts=True):
    """마지막 글자에 받침이 있나. 판단할 글자가 없으면 None.

    rieul_counts=False 는 ㄹ 받침을 '없음' 으로 센다 — '으로/로' 때문이다.
    ㄹ 받침은 '서울로', '연필로' 처럼 '로' 를 쓰고, 다른 받침만 '책으로',
    '손으로' 처럼 '으로' 다. 조사 중 이것만 예외다.

    괄호·점·공백은 건너뛰고 그 앞 글자를 본다 — '알파벳(구글)' 같은 이름 때문.
    """
    for ch in reversed(word or ""):
        if "가" <= ch <= "힣":                     # 한글 음절
            jong = (ord(ch) - 0xAC00) % 28
            if jong == 0:
                return False
            return True if rieul_counts else jong != RIEUL
        up = ch.upper()
        if "A" <= up <= "Z":
            if up not in _CONSONANT_LETTERS:
                return False
            # L 엘 · R 아르 는 ㄹ 받침이라 '으로' 의 예외에 해당한다
            return True if rieul_counts else up not in ("L", "R")
        if ch.isdigit():
            if ch not in _CONSONANT_DIGITS:
                return False
            # 1 일 · 7 칠 · 8 팔 은 ㄹ 받침
            return True if rieul_counts else ch not in ("1", "7", "8")
    return None


def josa(word, pair):
    """받침에 맞는 조사 하나. 판단할 수 없으면 받침 없는 쪽을 쓴다."""
    withf, without = PAIRS.get(pair, (pair, pair))
    f = has_final(word, rieul_counts=pair not in ("으로", "로"))
    return withf if f else without


def with_josa(word, pair):
    """'인텔' + '는' → '인텔은'."""
    return f"{word}{josa(word, pair)}"
