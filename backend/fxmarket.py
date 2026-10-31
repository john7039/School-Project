"""외환시장 개장 여부를 판정하는 곳 — 한 곳만 둔다.

collect_fx_live.py(받아올지 말지)와 fx_freshness.py(낡았다고 알릴지 말지)가
**같은 판정**을 써야 한다. 두 곳에 같은 규칙을 두면 한쪽만 고쳐져서
"장이 닫혔는데 숫자가 안 바뀐다고 알림이 오는" 오경보가 난다.

FX 는 뉴욕 금요일 17:00 에 닫고 일요일 17:00 에 연다. KST 로 환산하면
미국 서머타임에 따라 한 시간 움직인다 — 여름 06:00, 겨울 07:00.

그래서 경계를 넉넉하게 잡는다. **토요일 08:00 ~ 월요일 05:00** 만 휴장으로 본다.
넉넉한 쪽으로 틀리면 쓸모없는 호출 몇 번이 늘 뿐이지만, 좁게 잡으면 금요일 장
마지막 한 시간을 통째로 놓친다. (2026-10-31 실측: 봉이 토요일 07:05 까지 있었다)
"""
import datetime


def market_closed(now=None):
    """KST 기준 휴장이면 True."""
    now = now or datetime.datetime.now()
    wd, hour = now.weekday(), now.hour  # 월=0 … 토=5, 일=6
    if wd == 5 and hour >= 8:
        return True
    if wd == 6:
        return True
    if wd == 0 and hour < 5:
        return True
    return False


# ── 환율의 '하루' = 세션 ────────────────────────────────────────────────
#
# 서울외환시장 원/달러 거래시간은 2024-07-01 부터 09:00 ~ 다음날 02:00 이다.
# (그 전에는 09:00~15:30. 런던 시장 시간을 포괄해 외국인이 새벽에도 실시간
#  환율로 환전할 수 있게 하려고 연장했다. 연장 첫날 새벽 2시 마감가 1383.8원과
#  오후 3시 30분 종가 1379.3원이 4.5원 차이가 났다.)
#
# ⚠️ 그래서 환율의 하루를 **자정으로 자르면 안 된다.** 한 세션이 두 날짜에
#    걸쳐 있다. 자정 기준으로 자르면 "오늘 00:00~07:00" 이라고 띄운 그래프가
#    실은 **어제 세션의 꼬리토막**이 된다. 2026-10-31 에 실제로 그랬다.
#
# 시작가도 마찬가지다. 사용자가 "오늘 환율 어땠어" 라고 물을 때 기준은
# 자정 값이 아니라 **09:00 개장가**다.
#
# 수집은 24시간 계속한다 — 실측으로 새벽 03:00~08:00 에도 매 시간 12봉이
# 전부 다른 값이었다. 멈춘 값이 아니라 실제 거래다.
SESSION_OPEN_HOUR = 9
SESSION_CLOSE_HOUR = 2      # 다음날


def session_bounds(day):
    """day(YYYY-MM-DD) 세션의 [시작, 끝) — fx_intraday.ts 와 비교할 ISO 문자열."""
    d = datetime.date.fromisoformat(day)
    start = datetime.datetime.combine(d, datetime.time(SESSION_OPEN_HOUR, 0))
    end = datetime.datetime.combine(d + datetime.timedelta(days=1),
                                    datetime.time(SESSION_CLOSE_HOUR, 0))
    return start.isoformat(timespec="minutes"), end.isoformat(timespec="minutes")


def current_session_day(now=None):
    """지금 기준으로 '오늘' 세션의 시작 날짜.

    09:00 전이면 아직 오늘 장이 열리지 않았으므로 어제 세션을 가리킨다
    (00:00~02:00 이면 어제 세션 진행 중, 02:00~09:00 이면 어제 세션이 막 끝난 뒤).
    """
    now = now or datetime.datetime.now()
    d = now.date()
    if now.hour < SESSION_OPEN_HOUR:
        d -= datetime.timedelta(days=1)
    return d.isoformat()
