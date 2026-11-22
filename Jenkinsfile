// Niyam release pipeline.
// Every sh step uses single quotes so the shell, not Groovy, expands secrets.
// Every sh step starts with a shebang because the Windows controller's global
// shell setting points to a Windows path that does not exist on the Ubuntu agent.
pipeline {
  agent { label 'niyam-wsl' } // Ubuntu agent with Docker, Ansible and cluster access.

  triggers {
    githubPush()
    pollSCM('H/2 * * * *') // Fallback when the webhook relay is unavailable.
  }

  options {
    disableConcurrentBuilds()
    timeout(time: 45, unit: 'MINUTES')
    buildDiscarder(logRotator(numToKeepStr: '20'))
  }

  environment {
    DOCKERHUB_NS = 'freakun'
    INVENTORY = 'ansible/inventory/hosts.ini'
    ANSIBLE_CONFIG = "${WORKSPACE}/ansible/ansible.cfg"
    // Do not declare DEPLOYED here: environment values cannot be reassigned from script{}.
  }

  stages {
    stage('Init') {
      steps {
        script {
          env.IMAGE_TAG = sh(
            returnStdout: true,
            script: '#!/bin/bash\ngit rev-parse --short=7 HEAD'
          ).trim()
          currentBuild.displayName = "#${env.BUILD_NUMBER} ${env.IMAGE_TAG}"
        }
      }
    }

    stage('Unit tests') {
      steps {
        sh '''#!/bin/bash
          set -euo pipefail
          docker build -f services/api/Dockerfile --target test -t "niyam-api-test:$IMAGE_TAG" .
        '''
      }
    }

    stage('Build images') {
      steps {
        sh '''#!/bin/bash
          set -euo pipefail
          docker build -f services/api/Dockerfile --target runtime \
            --build-arg "APP_VERSION=$IMAGE_TAG" -t "$DOCKERHUB_NS/niyam-api:$IMAGE_TAG" .
          docker build --build-arg "APP_VERSION=$IMAGE_TAG" \
            -t "$DOCKERHUB_NS/niyam-web:$IMAGE_TAG" services/web
        '''
      }
    }

    // P5 (Teammate 2): add stage('Eval gate') here, using eval/run_eval.py.
    // P5 (Teammate 2): add stage('Scan') here, using Trivy on both images.

    stage('Push to Docker Hub') {
      steps {
        withCredentials([usernamePassword(
          credentialsId: 'dockerhub',
          usernameVariable: 'DH_USER',
          passwordVariable: 'DH_PASS'
        )]) {
          sh '''#!/bin/bash
            set -euo pipefail
            DOCKER_CONFIG="$(mktemp -d)"
            export DOCKER_CONFIG
            trap 'rm -rf "$DOCKER_CONFIG"' EXIT
            printf '%s' "$DH_PASS" | docker login -u "$DH_USER" --password-stdin
            docker push "$DOCKERHUB_NS/niyam-api:$IMAGE_TAG"
            docker push "$DOCKERHUB_NS/niyam-web:$IMAGE_TAG"
          '''
        }
      }
    }

    stage('Deploy (Ansible)') {
      steps {
        // P5 (Teammate 2): set env.DEPLOYED = 'true' here inside script{} for rollback.
        withCredentials([string(credentialsId: 'ansible-vault-pass', variable: 'ANSIBLE_VAULT_PASS')]) {
          sh '''#!/bin/bash
            set -euo pipefail
            ansible-playbook -i "$INVENTORY" ansible/playbooks/deploy.yml \
              -e "image_tag=$IMAGE_TAG" -e "dockerhub_ns=$DOCKERHUB_NS" \
              --vault-password-file ansible/scripts/vault-pass.sh
          '''
        }
      }
    }

    stage('Verify') {
      steps {
        sh '''#!/bin/bash
          set -euo pipefail
          bash scripts/smoke.sh "$IMAGE_TAG"
        '''
        // P5 (Teammate 2): add the live eval and mark_good.yml here.
      }
    }
  }

  post {
    // P5 (Teammate 2): add failure { } here to run rollback.yml when env.DEPLOYED == 'true'.
    cleanup {
      sh '''#!/bin/bash
        docker image rm "niyam-api-test:${IMAGE_TAG:-none}" \
          "$DOCKERHUB_NS/niyam-api:${IMAGE_TAG:-none}" \
          "$DOCKERHUB_NS/niyam-web:${IMAGE_TAG:-none}" >/dev/null 2>&1 || true
      '''
    }
  }
}
