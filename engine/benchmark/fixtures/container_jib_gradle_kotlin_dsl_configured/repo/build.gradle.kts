plugins { id("com.google.cloud.tools.jib") version "3.4.0" }

jib {
    from {
        image = "eclipse-temurin:21-jre"
    }
    to {
        image = "eu.gcr.io/acme/app"
        tags = setOf("latest")
    }
    container {
        ports = listOf("8080", "8081")
        mainClass = "com.acme.MainKt"
    }
}
