#!/bin/bash
set -u

BRAIN_PID=""
UVICORN_PID=""

cleanup() {
  echo "🛑 [start.sh] 종료 신호(SIGTERM/SIGINT) 수신: 실행 중인 프로세스를 정상 종료합니다..." >&2
  if [ -n "$BRAIN_PID" ] && kill -0 "$BRAIN_PID" 2>/dev/null; then
    kill -TERM "$BRAIN_PID" 2>/dev/null || true
  fi
  if [ -n "$UVICORN_PID" ] && kill -0 "$UVICORN_PID" 2>/dev/null; then
    kill -TERM "$UVICORN_PID" 2>/dev/null || true
  fi
  wait 2>/dev/null
  echo "✅ [start.sh] 모든 프로세스가 안전하게 종료되었습니다." >&2
  exit 0
}

trap cleanup SIGTERM SIGINT

# 지식 수집 엔진: 백그라운드 관리 루프
(
  trap 'exit 0' SIGTERM SIGINT
  while true; do
    python brain.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
      echo "💡 [start.sh] brain.py 정상 종료" >&2
    else
      echo "⚠️ [start.sh] brain.py 비정상 종료 (코드: $EXIT_CODE). 30초 후 재시작합니다." >&2
    fi
    sleep 30 &
    wait $!
  done
) &
BRAIN_PID=$!

# FastAPI 백엔드 (단일 워커 명시: In-memory Rate Limit 및 Persistent Disk 안정성 확보)
uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 &
UVICORN_PID=$!

wait "$UVICORN_PID"
cleanup
