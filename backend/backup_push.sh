#!/bin/bash
# VM 안의 백업을 호스트 맥 미니로 한 벌 더 보낸다.
#
# 왜 VM 밖으로 보내는가 —
#   /home/miniserver/backups 는 VM 안이다. VM 이미지가 깨지거나 실수로
#   지워지면 원본과 백업이 같이 사라진다. 한 벌은 VM 밖에 있어야 한다.
#
# 왜 rsync 가 아니라 scp 인가 (2026-10-26) —
#   rsync 는 SELinux 전용 도메인(rsync_t)을 가진다. systemd 가 실행하면
#   그 도메인으로 전이되는데, rsync_t 는 ssh 를 실행할 수 없고(불리언
#   rsync_client 로 품), 그다음엔 ~/.ssh/known_hosts(ssh_home_t)도 읽지
#   못했다. 거기까지 풀려면 커스텀 정책 모듈을 만들어야 한다.
#   scp 는 bin_t 라 도메인 전이가 없어 이 문제가 생기지 않는다.
#   하는 일이 작은 파일 몇 개 복사라 rsync 의 증분 기능이 아깝지 않다.
#   (로그인 셸에서 rsync 가 멀쩡히 되는 건 unconfined_t 라 전이가 없어서다)
#
# 왜 실패를 숨기지 않는가 (set -e) —
#   호스트는 VM 을 돌리는 기계라 VM 이 떠 있으면 반드시 켜져 있다.
#   그러므로 전송 실패는 "꺼져 있어서" 가 아니라 SSH·키·디스크 문제다.
#   조용히 넘어가면 몇 달 뒤 필요할 때 사본이 없다.
set -euo pipefail

HOST=john@192.168.64.1
SRC_DIR=/home/miniserver/backups
DEST=econ-backups
KEEP_DAYS=30
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)

ssh "${SSH_OPTS[@]}" "$HOST" "mkdir -p $DEST"

# 호스트에 이미 있는 파일 목록
remote=$(ssh "${SSH_OPTS[@]}" "$HOST" "ls -1 $DEST 2>/dev/null" || true)

today=$(date +%Y%m%d)
sent=0
for path in "$SRC_DIR"/econ-*.db; do
    [ -e "$path" ] || continue
    name=$(basename "$path")
    # 오늘 것은 내용이 바뀌었을 수 있으니 늘 다시 보낸다.
    # 지난 것은 이미 있으면 건너뛴다 (내용이 바뀔 일이 없다).
    if [ "$name" != "econ-$today.db" ] && grep -qxF "$name" <<<"$remote"; then
        continue
    fi
    scp -q "${SSH_OPTS[@]}" "$path" "$HOST:$DEST/$name"
    sent=$((sent + 1))
done

ssh "${SSH_OPTS[@]}" "$HOST" \
    "find $DEST -name 'econ-*.db' -type f -mtime +$KEEP_DAYS -delete"

n=$(ssh "${SSH_OPTS[@]}" "$HOST" "ls -1 $DEST/econ-*.db 2>/dev/null | wc -l" | tr -d ' ')
echo "호스트 전송 완료 — $HOST:~/$DEST · 보낸 파일 ${sent}개 · 보관 ${n}개 (${KEEP_DAYS}일)"
