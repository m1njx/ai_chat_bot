#!/bin/bash
set -u

# 지식 수집 엔진: 죽으면 30초 뒤 자동 재시작
(
  while true; do
    python brain.py
    echo "⚠️ brain.py 종료됨. 30초 후 재시작합니다." >&2
    sleep 30
  done
) &

# FastAPI 백엔드 (프론트엔드는 별도 배포)
exec uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}"
