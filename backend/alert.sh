#!/bin/bash
# 유닛이 실패했을 때 systemd 가 불러주는 알림 스크립트.
#
# 누가 부르는가 —
#   각 유닛의 [Unit] 에 OnFailure=econ-alert@%n.service 를 걸어 두었다.
#   %n 은 실패한 유닛의 전체 이름이고, 그게 템플릿 유닛의 인스턴스(%i)로
#   넘어와 이 스크립트의 첫 번째 인자가 된다.
#
# 왜 폴링하지 않는가 —
#   "몇 분마다 상태를 확인" 하는 방식은 확인 주기만큼 늦고, 확인하는 쪽이
#   죽으면 그것도 모른다. OnFailure 는 systemd 가 실패를 아는 바로 그 순간에
#   불러준다. 감시하는 쪽을 따로 둘 필요가 없다.
#
# 알림 내용에 무엇을 담는가 —
#   ntfy 는 토픽 이름을 아는 사람이면 누구나 구독할 수 있다. 그래서 유닛
#   이름·시각·종료 코드처럼 그 자체로는 쓸모없는 정보만 보내고, 로그 본문은
#   마지막 몇 줄로 제한한다. 자세한 건 서버에서 journalctl 로 본다.
set -uo pipefail

UNIT="${1:-unknown.service}"
ENV_FILE="/home/miniserver/School-Project/backend/.env"
HOST="$(hostname -s)"

TOPIC=""
[ -r "$ENV_FILE" ] && TOPIC=$(grep -E '^NTFY_TOPIC=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" )

# 상태 요약
ACTIVE=$(systemctl show "$UNIT" -p ActiveState --value 2>/dev/null)
RESULT=$(systemctl show "$UNIT" -p Result --value 2>/dev/null)
CODE=$(systemctl show "$UNIT" -p ExecMainStatus --value 2>/dev/null)
WHEN=$(date '+%Y-%m-%d %H:%M:%S')

# 마지막 로그 몇 줄 (너무 길면 알림이 잘린다)
LOG=$(journalctl -u "$UNIT" -n 6 --no-pager -o cat 2>/dev/null | tail -6)

BODY="$HOST · $WHEN
state=$ACTIVE result=$RESULT exit=$CODE

$LOG

확인: journalctl -u $UNIT -n 50"

# 로컬에도 남긴다 — 이 스크립트의 출력은 journal 로 들어간다
echo "[alert] $UNIT 실패 — result=$RESULT exit=$CODE"

if [ -z "$TOPIC" ]; then
    echo "[alert] NTFY_TOPIC 이 .env 에 없다 — 알림을 보내지 못했다" >&2
    exit 1
fi

if ! curl -sS -m 15 \
        -H "Title: $UNIT FAILED on $HOST" \
        -H "Priority: high" \
        -H "Tags: rotating_light" \
        -d "$BODY" \
        "https://ntfy.sh/$TOPIC" >/dev/null; then
    echo "[alert] ntfy 전송 실패" >&2
    exit 1
fi

echo "[alert] ntfy 전송 완료"
