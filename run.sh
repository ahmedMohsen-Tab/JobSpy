#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-jobspy-bot}"
CONTAINER_NAME="${CONTAINER_NAME:-jobspy-bot}"
BOT_TOKEN="${BOT_TOKEN:-}"
CHAT_ID="${CHAT_ID:-}"
GROQ_API_KEY="${GROQ_API_KEY:-}"

case "${1:-run}" in
  build)
    docker build -t "$IMAGE_NAME" .
    ;;
  run)
    docker build -t "$IMAGE_NAME" .
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

    # Preserve history across runs; create file only if it does not exist
    if [ ! -f "$(pwd)/notified_jobs.json" ]; then
      echo "[]" > "$(pwd)/notified_jobs.json"
    fi

    docker run --rm \
      --name "$CONTAINER_NAME" \
      -e BOT_TOKEN="$BOT_TOKEN" \
      -e CHAT_ID="$CHAT_ID" \
      -e GROQ_API_KEY="$GROQ_API_KEY" \
      -v "$(pwd)/JsonConfigurqation.json:/app/JsonConfigurqation.json:ro" \
      -v "$(pwd)/notified_jobs.json:/app/notified_jobs.json" \
      "$IMAGE_NAME"
    ;;
  *)
    echo "Usage: $0 [build|run]"
    exit 1
    ;;
esac
