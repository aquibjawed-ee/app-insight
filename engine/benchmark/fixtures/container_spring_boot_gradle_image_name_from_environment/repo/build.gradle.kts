plugins { id("org.springframework.boot") version "3.2.0" }

tasks.bootBuildImage {
    imageName.set(System.getenv("IMAGE_NAME"))
}
