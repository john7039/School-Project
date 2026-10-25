"""뉴스 잡음(실제 경제 기사가 아닌 것) 필터.

두 종류를 거른다.
  1) 기사가 아닌 것 — Finnhub company-news 에 섞여 들어오는 SEC 공시(Form 4 등)
     과 시세/견적 페이지.
  2) 경제와 무관한 것 — 한국어 뉴스를 검색으로 받아오면서 생겼다. '기아' 를
     검색했더니 기아 타이거즈 야구 기사가 올라왔다.

수집(collect_news, rss_search)과 읽기(curate/company_curate) 양쪽에서 쓴다.
"""
import re

JUNK_RE = re.compile(
    r"^\s*form\s+\d"                                              # SEC 공시: Form 4 / 3 / 144 / 8.3 / 13F ...
    r"|(stock|share)\s+price[,\s].*(news|quote|market\s*cap|chart|history)"  # 시세/견적 페이지
    r"|quote\s*&\s*(history|chart)"
    r"|stock\s*market\s*cap",                                     # "... Stock Market Cap" 시세 페이지
    re.I,
)

# 경제와 무관한 분야. 한국어 기사에서만 쓸 일이 많지만 영어도 같이 둔다.
#
# 고르는 기준 — "이 단어가 제목에 있으면 경제 기사일 리가 없다" 만 넣는다.
# 애매한 건 넣지 않았다:
#   · '경기' — "야구 경기" 와 "경기 침체" 가 같은 글자다. 절대 못 쓴다.
#   · '감독' — 금융'감독'원이 있다.
#   · '드라마'·'영화' — 넷플릭스·디즈니 실적 기사에 늘 나온다.
#   · 정치 — 관세·금리 정책·규제는 정치 기사이면서 경제의 핵심이다.
#     선거·공천 같은 것만 좁게 넣었다.
OFFTOPIC_RE = re.compile(
    # 스포츠
    r"프로야구|메이저리그|KBO|K리그|프리미어리그|분데스리가|플레이오프|"
    r"한국시리즈|올림픽|월드컵|아시안게임|월드시리즈|"
    r"투수|타자|홈런|안타|득점|실점|선발\s*등판|완투|세이브|"
    r"좌타|우타|타선|타율|방어율|불펜|마운드|이닝|구원\s*등판|선발진|"
    r"타이거즈|라이온즈|베어스|트윈스|위즈|이글스|다이노스|랜더스|히어로즈|"
    r"골키퍼|코너킥|페널티킥|자책골|결승골|"
    r"야구|축구|농구|배구|골프|테니스|복싱|격투기|e스포츠|이스포츠|"
    r"우천\s*취소|경기장|구단|리그\s*우승|포스트시즌|\d+차전|연패|"
    # 'PO서 맞붙는다' 처럼 약어로 쓰는 경우. 뒤에 한글 조사가 붙어서
    # \b 로는 안 잡힌다. IPO 에 걸리지 않게 앞에 영문자가 없을 때만 본다.
    r"(?<![A-Za-z])PO(?![A-Za-z])|"
    r"\bNBA\b|\bMLB\b|\bNFL\b|\bNHL\b|\bUFC\b|\bLCK\b|"
    # 연예
    r"아이돌|예능|콘서트|앨범|팬미팅|시청률|열애|결별|음원\s*차트|"
    r"연예인|배우\s|가수\s|데뷔|컴백\s*무대|시상식|"
    # 사건·사고
    r"살인|성폭행|성추행|음주운전|뺑소니|보이스피싱\s*검거|"
    r"화재\s*발생|실종|부고|별세|빈소|"
    # 생활
    r"운세|로또\s*당첨|레시피|맛집|여행\s*코스|"
    # 선거 정치 (정책 기사는 남긴다)
    r"총선|대선|지방선거|공천|출마\s*선언|유세",
    re.I,
)


def is_junk(title):
    """실제 기사가 아니면 True (공시·시세 페이지·너무 짧은 제목)."""
    t = (title or "").strip()
    if len(t) < 15:
        return True
    return bool(JUNK_RE.search(t))


def is_offtopic(title):
    """경제와 무관한 분야면 True (스포츠·연예·사건사고·선거)."""
    return bool(OFFTOPIC_RE.search(title or ""))


# 뉴스가 아닌 출처. Google 뉴스에는 개인 블로그 글도 섞여 들어온다.
# '네이버' 를 검색했더니 "수원 인계동 카페 후기 : 네이버 블로그" 가 나왔다.
# 검색어 자체가 매체 이름일 때 특히 심하다.
BAD_SOURCE = re.compile(
    r"블로그|blog|브런치|brunch|티스토리|tistory|"
    r"카페|cafe\.|포스트|post\.naver|"
    r"스포츠조선|스포츠동아|스포츠서울|스포츠월드|일간스포츠|스타뉴스|"
    r"엑스포츠|OSEN|마이데일리|인터풋볼|루키",
    re.I,
)


def is_bad_source(source):
    """뉴스 매체가 아니면 True (개인 블로그·스포츠지)."""
    return bool(BAD_SOURCE.search(source or ""))


def keep(title, source=""):
    """수집·선별에서 살릴 기사면 True."""
    return (not is_junk(title)
            and not is_offtopic(title)
            and not is_bad_source(source))
