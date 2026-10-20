#!/bin/sh
# Keep the previous container until the replacement passes its healthcheck.
set -eu
: "${IMAGE_NAME:?}" "${BUILD_NUMBER:?}" "${CONTAINER_NAME:?}" "${ENV_FILE:?}"
: "${RAG_NETWORK:?}" "${MODEL_VOLUME:?}" "${CORPUS_VOLUME:?}"
: "${HOST_PORT:?}" "${CONTAINER_PORT:?}"
image="$IMAGE_NAME:$BUILD_NUMBER"
backup="$CONTAINER_NAME-previous"
HEALTH_ATTEMPTS=${HEALTH_ATTEMPTS:-60}
HEALTH_DELAY=${HEALTH_DELAY:-10}

if docker container inspect "$backup" >/dev/null 2>&1; then
  echo 'A previous deployment backup already exists. Inspect it before retrying.' >&2
  exit 1
fi

docker network inspect "$RAG_NETWORK" >/dev/null 2>&1 || docker network create "$RAG_NETWORK"
docker volume inspect "$MODEL_VOLUME" >/dev/null 2>&1 || docker volume create "$MODEL_VOLUME"
docker volume inspect "$CORPUS_VOLUME" >/dev/null 2>&1 || docker volume create "$CORPUS_VOLUME"

# Repair existing volume ownership without running the service as root.
docker run --rm --user root --entrypoint python \
  --env RAG_DATA_DIR=/app/data \
  --mount "type=volume,src=$CORPUS_VOLUME,dst=/app/data" \
  --mount "type=volume,src=$MODEL_VOLUME,dst=/models" \
  "$image" /app/container_entrypoint.py --prepare-volumes

# Build and check the target embedding release while production still uses its old alias.
deployment_id="deploy-$BUILD_NUMBER-$(date +%s)-$$"
release_command() {
  docker run --rm --network "$RAG_NETWORK" --env-file "$ENV_FILE" \
    --env RAG_DATA_DIR=/app/data --env RAG_SOURCE_DIR=/app/data/sources \
    --env HF_HOME=/models/huggingface --env FASTEMBED_CACHE_PATH=/models/fastembed \
    --mount "type=volume,src=$CORPUS_VOLUME,dst=/app/data" \
    --mount "type=volume,src=$MODEL_VOLUME,dst=/models" \
    "$image" "$@"
}
release_command --prepare-release "$deployment_id"
release_command --check-release "$deployment_id"

old_stopped=false
old_renamed=false
new_attempted=false
publication_attempted=false
rollback() {
  result=$?
  trap - EXIT HUP INT TERM
  if [ "$result" -ne 0 ]; then
    recoverable=true
    if [ "$new_attempted" = true ]; then
      docker logs --tail 60 "$CONTAINER_NAME" || true
      docker rm -f "$CONTAINER_NAME" || recoverable=false
    fi
    if [ "$publication_attempted" = true ]; then
      release_command --rollback-release "$deployment_id" || recoverable=false
    fi
    if [ "$old_renamed" = true ]; then
      docker rename "$backup" "$CONTAINER_NAME" || recoverable=false
    fi
    if [ "$old_stopped" = true ]; then
      if [ "$recoverable" = true ] && docker start "$CONTAINER_NAME"; then
        echo 'Previous retrieval container restored.' >&2
      else
        echo 'Manual recovery required: the previous container could not be restarted.' >&2
      fi
    elif [ "$recoverable" != true ]; then
      echo 'Manual recovery required: failed container cleanup did not complete.' >&2
    fi
  fi
  exit "$result"
}
trap rollback EXIT
trap 'exit 130' HUP INT TERM

if docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  docker stop "$CONTAINER_NAME"
  old_stopped=true
  docker rename "$CONTAINER_NAME" "$backup"
  old_renamed=true
fi

# Change the stable alias only after the old service has stopped.
publication_attempted=true
release_command --publish-release "$deployment_id"

new_attempted=true
docker run -d --name "$CONTAINER_NAME" --network "$RAG_NETWORK" \
  --restart unless-stopped \
  --publish "127.0.0.1:$HOST_PORT:$CONTAINER_PORT" \
  --env-file "$ENV_FILE" \
  --env RAG_DATA_DIR=/app/data --env RAG_SOURCE_DIR=/app/data/sources \
  --env HF_HOME=/models/huggingface --env FASTEMBED_CACHE_PATH=/models/fastembed \
  --mount "type=volume,src=$CORPUS_VOLUME,dst=/app/data" \
  --mount "type=volume,src=$MODEL_VOLUME,dst=/models" \
  "$image"

attempt=0
healthy=false
while [ "$attempt" -lt "$HEALTH_ATTEMPTS" ]; do
  attempt=$((attempt + 1))
  state=$(docker inspect --format '{{.State.Status}}' "$CONTAINER_NAME")
  health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$CONTAINER_NAME")
  if [ "$state" = running ] && [ "$health" = healthy ]; then
    healthy=true
    break
  fi
  if [ "$state" != running ] || [ "$health" = unhealthy ] || [ "$health" = missing ]; then
    echo 'Replacement container failed its healthcheck.' >&2
    exit 1
  fi
  sleep "$HEALTH_DELAY"
done
if [ "$healthy" != true ]; then
  echo 'Timed out waiting for retrieval readiness.' >&2
  exit 1
fi

# Deployment is now committed; cleanup failure must not roll back a healthy service.
trap - EXIT HUP INT TERM
if [ "$old_renamed" = true ]; then
  docker rm "$backup" || echo 'Healthy deployment; old stopped container needs cleanup.' >&2
fi
docker tag "$image" "$IMAGE_NAME:latest" || echo 'Healthy deployment; latest tag could not be updated.' >&2
echo 'Retrieval deployment passed its healthcheck.'
