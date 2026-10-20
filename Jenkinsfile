pipeline {
  agent any

  options {
    skipDefaultCheckout()
    disableConcurrentBuilds()
    timestamps()
    timeout(time: 30, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '10'))
  }

  environment {
    IMAGE_NAME = 'vietflood-retrieval'
    CONTAINER_NAME = 'rag-retrieval'
    HOST_PORT = '8001'
    CONTAINER_PORT = '8001'
    ENV_FILE = '/opt/env/vietflood-rag.env'
    RAG_NETWORK = 'jenkins_default'
    MODEL_VOLUME = 'vietflood-rag-models'
    CORPUS_VOLUME = 'vietflood-rag-data'
  }

  stages {
    stage('Checkout') {
      steps {
        deleteDir()
        checkout scm
        script {
          if (fileExists('Dockerfile')) {
            env.APP_DIR = '.'
          } else if (fileExists('VietFlood/Dockerfile')) {
            env.APP_DIR = 'VietFlood'
          } else {
            error('Dockerfile was not found in the repository root or VietFlood/.')
          }
        }
      }
    }

    stage('Validate deployment configuration') {
      steps {
        sh '''
          set +x
          set -eu
          test -f "$ENV_FILE" || { echo "Missing deployment env file: $ENV_FILE"; exit 1; }
          grep -q '^RAG_SERVICE_TOKEN=.' "$ENV_FILE" || { echo 'RAG_SERVICE_TOKEN is required.'; exit 1; }
          grep -q '^RAG_ADMIN_TOKEN=.' "$ENV_FILE" || { echo 'RAG_ADMIN_TOKEN is required for uploads.'; exit 1; }
          grep -q '^QDRANT_URL=.' "$ENV_FILE" || { echo 'QDRANT_URL is required.'; exit 1; }
          if [ -f "$APP_DIR/check_embedding_runtime.py" ]; then
            grep -q '^OPENAI_API_KEY=.' "$ENV_FILE" || { echo 'OPENAI_API_KEY is required.'; exit 1; }
          fi
        '''
      }
    }

    stage('Build image') {
      steps {
        dir("${APP_DIR}") {
          sh '''
            set +x
            set -eu
            revision=$(git rev-parse HEAD)
            docker build --pull \
              --label org.opencontainers.image.revision="$revision" \
              -t "$IMAGE_NAME:$BUILD_NUMBER" .
          '''
        }
      }
    }

    stage('Check embedding provider') {
      steps {
        sh '''
          set +x
          set -eu
          if [ -f "$APP_DIR/check_embedding_runtime.py" ]; then
            docker run --rm --env-file "$ENV_FILE" --entrypoint python \
              "$IMAGE_NAME:$BUILD_NUMBER" /app/check_embedding_runtime.py
          fi
        '''
      }
    }

    stage('Deploy and verify') {
      steps {
        sh '''
          set +x
          set -eu
          sh "$APP_DIR/deploy_rag.sh"
        '''
      }
    }
  }

  post {
    success {
      echo "Retrieval image deployed and verified: ${IMAGE_NAME}:${BUILD_NUMBER}"
    }
    failure {
      echo 'Deployment failed. Check preflight and rollback logs before retrying.'
    }
  }
}
