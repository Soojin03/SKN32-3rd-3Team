#!/usr/bin/env bash

# 명령 실행 중 오류가 발생하면 즉시 스크립트를 종료합니다.
set -e

# 현재 스크립트가 위치한 프로젝트 루트 디렉터리로 이동합니다.
cd "$(dirname "$0")"

# .env 파일이 존재하면 환경변수를 현재 셸 세션에 로드합니다.
if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

# HOST가 설정되어 있지 않으면 외부 접속 허용(0.0.0.0)을 기본값으로 사용합니다.
HOST="${HOST:-0.0.0.0}"

# PORT가 설정되어 있지 않으면 8000번 포트를 기본값으로 사용합니다.
PORT="${PORT:-8000}"

# Uvicorn을 통해 FastAPI 애플리케이션을 구동합니다.
exec uvicorn app.main:app --host "${HOST}" --port "${PORT}" --workers 1