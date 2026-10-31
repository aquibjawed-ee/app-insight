plugins { id("org.springframework.boot") version "3.2.0" }

tasks.bootBuildImage {
    imageName.set("acme/app")
    builder.set("paketobuildpacks/builder-jammy-base")
    runImage.set("paketobuildpacks/run-jammy-base")
    publish.set(true)
    docker {
        publishRegistry {
            url.set("https://eu.gcr.io")
        }
    }
}
