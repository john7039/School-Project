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
