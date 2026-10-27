#!/bin/bash
# 매일 아침, 어제까지의 상태가 멀쩡한지 확인한다.
#
# 왜 필요한가 —
#   OnFailure 는 유닛이 "실패" 할 때만 불린다. 타이머가 꺼져 있거나 그 시각에
#   VM 이 안 켜져 있어서 **아예 실행되지 않은** 경우에는 실패도 없으므로
#   아무 일도 일어나지 않는다. 조용한 것과 정상인 것을 구분하려면 누군가
#   "있어야 할 결과가 있는지" 를 따로 봐야 한다.
#
# 알림은 어떻게 가는가 —
#   이 스크립트가 0 이 아닌 값으로 끝나면 econ-healthcheck.service 가 실패하고,
#   거기 걸린 OnFailure 가 평소와 같은 알림 유닛을 부른다. 알림 경로를 새로
#   만들지 않았다.
set -uo pipefail

BACKUP_DIR=/home/miniserver/backups
HOST=john@192.168.64.1
HOST_DIR=econ-backups
DISK_LIMIT=85                 # %
STALE_HOURS=26                # 하루 한 번 도는 작업의 허용 간격

today=$(date +%Y%m%d)
fail=0

ok()  { printf "  OK    %s\n" "$1"; }
bad() { printf "  실패  %s\n" "$1"; fail=1; }

echo "점검 $(date '+%Y-%m-%d %H:%M')"

# ── 1. 오늘 백업이 VM 에 있는가 ──
if [ -s "$BACKUP_DIR/econ-$today.db" ]; then
    ok "VM 백업 econ-$today.db ($(du -h "$BACKUP_DIR/econ-$today.db" | cut -f1))"
else
    bad "VM 백업 econ-$today.db 가 없다"
fi

# ── 2. 호스트에도 갔는가 ──
if ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" \
       "test -s $HOST_DIR/econ-$today.db" 2>/dev/null; then
    ok "호스트 백업 econ-$today.db"
else
    bad "호스트 백업 econ-$today.db 가 없다 (전송 실패 또는 호스트 접속 불가)"
fi

# ── 3. 하루 한 번 도는 유닛들이 최근에, 성공으로 끝났는가 ──
for u in econ-collect.service econ-fx.service econ-backup.service; do
    res=$(systemctl show "$u" -p Result --value)
    ts=$(systemctl show "$u" -p ExecMainStartTimestamp --value)
    if [ -z "$ts" ]; then
        bad "$u 실행 기록이 없다"
        continue
    fi
    age=$(( ( $(date +%s) - $(date -d "$ts" +%s) ) / 3600 ))
    if [ "$res" != "success" ]; then
        bad "$u 마지막 결과가 $res"
    elif [ "$age" -gt "$STALE_HOURS" ]; then
        bad "$u 가 ${age}시간째 실행되지 않았다 (허용 ${STALE_HOURS}시간)"
    else
        ok "$u ${age}시간 전 · success"
    fi
done

# ── 4. 상시 실행 서비스 ──
for u in nginx econ-backend tailscaled ollama; do
    st=$(systemctl is-active "$u")
    [ "$st" = "active" ] && ok "$u $st" || bad "$u 가 $st"
done

# ── 5. 디스크 ──
while read -r use mnt; do
    n=${use%\%}
    [ "$n" -lt "$DISK_LIMIT" ] && ok "디스크 $mnt $use" \
                               || bad "디스크 $mnt $use (한계 ${DISK_LIMIT}%)"
done < <(df --output=pcent,target / /home | tail -n +2)

echo
if [ "$fail" -eq 0 ]; then
    echo "전부 정상"
else
    echo "문제가 있다 — 위의 '실패' 줄 참고"
fi
exit "$fail"
