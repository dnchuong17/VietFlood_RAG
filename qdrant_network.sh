#!/bin/sh
# Source this file before every deployment probe and rollout. No env-file eval.
rag_env_value() {
  if [ -f "$ENV_FILE" ]; then
    awk -v key="$1" 'index($0, key "=") == 1 {value=substr($0,length(key)+2)} END {print value}' "$ENV_FILE"
  fi
}

QDRANT_INTERNAL_URL=${QDRANT_INTERNAL_URL:-$(rag_env_value QDRANT_INTERNAL_URL)}
if [ -z "$QDRANT_INTERNAL_URL" ] && [ "${QDRANT_LOCAL_DOCKER:-0}" = 1 ]; then
  qdrant_container=${QDRANT_CONTAINER:-$(rag_env_value QDRANT_CONTAINER)}
  if [ -z "$qdrant_container" ]; then
    qdrant_candidates=$(docker ps --format '{{.Names}} {{.Image}}' |
      awk '$2 ~ /(^|\/)qdrant\/qdrant(:|@|$)/ {print $1}')
    # Docker container names cannot contain whitespace or shell glob characters.
    set -- $qdrant_candidates
    if [ "$#" -ne 1 ]; then
      echo 'Set QDRANT_CONTAINER in the deployment env file: expected one running official Qdrant container.' >&2
      exit 1
    fi
    qdrant_container=$1
  fi
  case "$qdrant_container" in
    ''|*[!a-zA-Z0-9_.-]*) echo 'Invalid QDRANT_CONTAINER.' >&2; exit 1 ;;
  esac
  qdrant_running=$(docker inspect --format '{{.State.Running}}' "$qdrant_container")
  if [ "$qdrant_running" != true ]; then
    echo 'Qdrant container must be running before deployment.' >&2
    exit 1
  fi
  qdrant_container=$(docker inspect --format '{{.Name}}' "$qdrant_container")
  qdrant_container=${qdrant_container#/}
  docker network inspect "$RAG_NETWORK" >/dev/null 2>&1 || docker network create "$RAG_NETWORK"
  qdrant_members=$(docker network inspect --format '{{range .Containers}}{{println .Name}}{{end}}' "$RAG_NETWORK")
  if ! printf '%s\n' "$qdrant_members" | grep -Fxq -- "$qdrant_container"; then
    docker network connect "$RAG_NETWORK" "$qdrant_container"
  fi
  QDRANT_INTERNAL_URL="http://$qdrant_container:6333"
  echo 'Qdrant transport: direct Docker network (REST port 6333).' >&2
fi
export QDRANT_INTERNAL_URL
