"""뉴스 잡음(실제 기사가 아닌 것) 필터.
Finnhub company-news 피드에는 SEC 공시(Form 4 등)·시세/견적 페이지가 섞여 들어옴.
수집(collect_news)과 읽기(curate/company_curate/refresh) 양쪽에서 공통으로 사용."""
import re

JUNK_RE = re.compile(
    r"^\s*form\s+\d"                                              # SEC 공시: Form 4 / 3 / 144 / 8.3 / 13F ...
    r"|(stock|share)\s+price[,\s].*(news|quote|market\s*cap|chart|history)"  # 시세/견적 페이지
    r"|quote\s*&\s*(history|chart)"
    r"|stock\s*market\s*cap",                                     # "... Stock Market Cap" 시세 페이지
    re.I,
)


def is_junk(title):
    """실제 기사가 아니면 True (공시·시세 페이지·너무 짧은 제목)."""
    t = (title or "").strip()
    if len(t) < 15:
        return True
    return bool(JUNK_RE.search(t))
