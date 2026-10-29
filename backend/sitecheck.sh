#!/bin/bash
# 사이트가 실제로 응답하는지 5분마다 본다.
#
# 왜 필요한가 (2026-10-29 장애 훈련에서 드러남) —
#   nginx 의 proxy_pass 포트를 8000 → 8001 로 바꿔 놓으니 사이트에서 데이터가
#   전부 사라졌는데, **알림이 한 통도 오지 않았다.** nginx 도 uvicorn 도 각자
#   멀쩡히 떠 있었고 systemd 입장에서는 실패한 유닛이 없었기 때문이다.
#
#   기존 감시 셋이 전부 '서버 안쪽' 만 본다 —
#     OnFailure    유닛이 실패해야 불린다
#     헬스체크      유닛 상태·백업·디스크
#     수집 리포트    DB 내용
#   "밖에서 실제로 응답이 오는가" 를 보는 것이 하나도 없었다.
#   실제 장애였다면 사용자가 알려줄 때까지 몰랐을 것이다.
#
# 두 경로를 따로 재는 이유 —
#   안쪽(127.0.0.1)은 nginx→uvicorn 만, 바깥(공개 주소)은 Funnel 까지 포함한다.
#   안쪽은 되는데 바깥만 안 되면 Funnel 문제다. 한쪽만 재면 그 구분이 안 된다.
#
# 알림을 상태가 바뀔 때만 보내는 이유 —
#   5분마다 울리면 한 시간 장애에 12통이 온다. 그러면 사람이 알림을 무시하기
#   시작한다. 고장났을 때 한 번, 돌아왔을 때 한 번만 보낸다.
#
# 깜빡임(blip)에 속지 않으려고 한 번 실행에서 두 번 시도한다.
set -uo pipefail

PUBLIC="https://macmini.tail1ca8bf.ts.net"
LOCAL="http://127.0.0.1"
STATE="/var/tmp/econ-sitecheck.state"
ENV_FILE="/home/miniserver/School-Project/backend/.env"
MIN_BYTES=100            # 200 인데 내용이 비어 있는 경우를 걸러낸다
HOSTNAME_S="$(hostname -s)"

# 한 번 재기: URL 이 200 이고 본문이 MIN_BYTES 이상이면 성공
probe() {
    local url="$1" out code size
    out=$(curl -s -o /dev/null -m 12 -w "%{http_code} %{size_download}" "$url" 2>/dev/null) || return 1
    code=${out% *}; size=${out#* }
    [ "$code" = "200" ] && [ "$size" -ge "$MIN_BYTES" ]
}

# 두 번 시도 (10초 간격) — 순간적인 실패는 넘긴다
check() {
    probe "$1" && return 0
    sleep 10
    probe "$1"
}

FAILED=""
for target in "$LOCAL/api/daily|내부 nginx→uvicorn" \
              "$PUBLIC/api/daily|공개 주소(Funnel 포함)" \
              "$PUBLIC/|화면"; do
    url=${target%%|*}; name=${target##*|}
    if check "$url"; then
        echo "  OK    $name"
    else
        echo "  실패  $name  ($url)"
        FAILED="${FAILED:+$FAILED; }$name"
    fi
done

NOW=$(date '+%Y-%m-%d %H:%M:%S')
PREV=$(cat "$STATE" 2>/dev/null || echo "unknown")
CUR=$([ -z "$FAILED" ] && echo "up" || echo "down")
echo "$CUR" > "$STATE"

[ "$PREV" = "$CUR" ] && { echo "상태 그대로($CUR) — 알림 없음"; exit 0; }

TOPIC=""
[ -r "$ENV_FILE" ] && TOPIC=$(grep -E '^NTFY_TOPIC=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"'"'" )
[ -z "$TOPIC" ] && { echo "NTFY_TOPIC 이 없다 — 알림 못 보냄" >&2; exit 1; }

if [ "$CUR" = "down" ]; then
    TITLE="사이트 응답 없음 on $HOSTNAME_S"; PRIO="urgent"; TAGS="rotating_light"
    BODY="$NOW

실패: $FAILED

유닛이 전부 정상이어도 이럴 수 있다.
확인: curl -i $PUBLIC/api/daily
      sudo tail -20 /var/log/nginx/error.log"
else
    TITLE="사이트 복구됨 on $HOSTNAME_S"; PRIO="default"; TAGS="white_check_mark"
    BODY="$NOW

세 가지 모두 정상으로 돌아왔다."
fi

curl -sS -m 15 -H "Title: $TITLE" -H "Priority: $PRIO" -H "Tags: $TAGS" \
     -d "$BODY" "https://ntfy.sh/$TOPIC" >/dev/null \
  && echo "알림 전송: $PREV → $CUR" \
  || { echo "ntfy 전송 실패" >&2; exit 1; }
