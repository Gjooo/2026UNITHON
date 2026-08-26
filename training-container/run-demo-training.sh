#!/usr/bin/env bash
# 학습을 실행하고, 어떤 경로로 끝나든 완료 결과를 백엔드에 정확히 한 번 알린다.
#
# 이 스크립트의 책임은 학습 자체가 아니라 "결과가 반드시 전달되는 것"이다.
# 학습이 성공하든, 실패하든, 스크립트가 중간에 죽든 백엔드는 결과를 받아야 한다.
# 결과가 오지 않으면 백엔드는 최대 실행시간까지 기다린 뒤 실패로 처리하고 GPU를 종료한다.
set -uo pipefail

COMPLETION_URL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --completion-url) COMPLETION_URL="${2:-}"; shift 2 ;;
    *) echo "알 수 없는 인자: $1" >&2; shift ;;
  esac
done
[ -n "$COMPLETION_URL" ] && export UNWORK_COMPLETION_URL="$COMPLETION_URL"

LOG_FILE="$(mktemp)"
REPORTED=""

report() {
  # 두 번 보내지 않는다. 백엔드는 실행 중 상태에서 한 번만 callback을 받는다.
  [ -n "$REPORTED" ] && return 0
  REPORTED=1
  python3 "$(dirname "$0")/report_completion.py" --exit-code "$1" --log-file "$LOG_FILE"
}

on_exit() {
  # 학습 명령이 신호로 죽어도 결과는 나간다.
  report "${EXIT_CODE:-1}"
  rm -f "$LOG_FILE"
}
trap on_exit EXIT

TRAINING_COMMAND="${TRAINING_COMMAND:-python3 train_sd15_lora.py}"
# 래퍼 자신의 로그는 완료 메시지에 섞이지 않도록 로그 파일에 넣지 않는다.
echo "학습을 시작합니다: ${TRAINING_COMMAND}"

set +e
# 로그는 Runpod 콘솔과 백엔드 전달용으로 동시에 남긴다.
eval "$TRAINING_COMMAND" 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE="${PIPESTATUS[0]}"
set -e

echo "학습이 종료되었습니다. exit=${EXIT_CODE}"
exit "$EXIT_CODE"
