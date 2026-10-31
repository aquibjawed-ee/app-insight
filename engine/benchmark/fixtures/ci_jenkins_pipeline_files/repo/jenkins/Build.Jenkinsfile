pipeline {
  stages {
    stage('Build') {
      steps { sh 'mvn clean install --batch-mode' }
    }
    stage('Tag release') {
      steps { sh 'git tag v1 && git push --tags' }
    }
    stage('Deploy to FAT') {
      steps { sh './deploy.sh' }
    }
  }
}
