pipeline {
  agent any

  options {
    skipDefaultCheckout()
    disableConcurrentBuilds()
    timestamps()
    buildDiscarder(logRotator(numToKeepStr: '10'))
  }

  environment {
    APP_DIR = 'VietFlood'
    IMAGE_NAME = 'vietflood-retrieval'
    CONTAINER_NAME = 'rag-retrieval'
    HOST_PORT = '8001'
    CONTAINER_PORT = '8001'
    ENV_FILE = '/opt/env/vietflood-rag.env'
    RAG_NETWORK = 'jenkins_default'
    MODEL_VOLUME = 'vietflood-rag-models'
    RAG_CORPUS_DIR = '/opt/vietflood/rag-data'
  }

  stages {
    stage('Checkout') {
      steps {
        deleteDir()
        checkout scm
      }
    }

    stage('Validate deployment configuration') {
      steps {
        sh '''
          set +x
          set -eu
          test -f "$ENV_FILE" || { echo "Missing deployment env file: $ENV_FILE"; exit 1; }
          test -d "$RAG_CORPUS_DIR" || { echo "Set RAG_CORPUS_DIR to the prepared RAG data directory on the Jenkins host."; exit 1; }
          grep -q '^RAG_SERVICE_TOKEN=.' "$ENV_FILE" || { echo "RAG_SERVICE_TOKEN is required in $ENV_FILE"; exit 1; }
          grep -q '^QDRANT_URL=.' "$ENV_FILE" || { echo "QDRANT_URL is required in $ENV_FILE"; exit 1; }
        '''
      }
    }

    stage('Build image') {
      steps {
        dir("${APP_DIR}") {
          sh '''
            set +x
            set -eu
            docker build --pull \
              --label org.opencontainers.image.revision="$GIT_COMMIT" \
              -t "$IMAGE_NAME:$BUILD_NUMBER" \
              -t "$IMAGE_NAME:latest" .
          '''
        }
      }
    }

    stage('Deploy') {
      steps {
        sh '''
          set +x
          set -eu
          docker network inspect "$RAG_NETWORK" >/dev/null 2>&1 || docker network create "$RAG_NETWORK"
          docker volume inspect "$MODEL_VOLUME" >/dev/null 2>&1 || docker volume create "$MODEL_VOLUME"

          docker stop "$CONTAINER_NAME" >/dev/null 2>&1 || true
          docker rm "$CONTAINER_NAME" >/dev/null 2>&1 || true

          docker run -d \
            --name "$CONTAINER_NAME" \
            --network "$RAG_NETWORK" \
            --restart unless-stopped \
            --publish "127.0.0.1:$HOST_PORT:$CONTAINER_PORT" \
            --env-file "$ENV_FILE" \
            --env RAG_DATA_DIR=/app/data \
            --env HF_HOME=/models/huggingface \
            --env FASTEMBED_CACHE_PATH=/models/fastembed \
            --mount "type=bind,src=$RAG_CORPUS_DIR,dst=/app/data,readonly" \
            --mount "type=volume,src=$MODEL_VOLUME,dst=/models" \
            "$IMAGE_NAME:$BUILD_NUMBER"

          echo "Container started. Check readiness at http://127.0.0.1:$HOST_PORT/health/ready from the host."
        '''
      }
    }

    stage('Wait for readiness') {
      steps {
        sh '''
          set +x
          set -eu
          for attempt in $(seq 1 60); do
            health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "$CONTAINER_NAME")
            if [ "$health" = healthy ]; then
              echo 'Retrieval service is healthy.'
              exit 0
            fi
            if [ "$health" = unhealthy ]; then
              echo 'Retrieval service health check failed.'
              docker logs --tail 80 "$CONTAINER_NAME" || true
              exit 1
            fi
            sleep 10
          done
          echo 'Timed out waiting for retrieval service readiness.'
          docker logs --tail 80 "$CONTAINER_NAME" || true
          exit 1
        '''
      }
    }
  }

  post {
    success {
      echo "VietFlood retrieval image deployed: ${IMAGE_NAME}:${BUILD_NUMBER}"
    }
    failure {
      echo 'VietFlood retrieval deployment failed; inspect the Jenkins stage output and container logs.'
    }
  }
}
