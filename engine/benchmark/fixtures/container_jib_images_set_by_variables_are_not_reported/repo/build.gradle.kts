plugins { id("com.google.cloud.tools.jib") version "3.4.0" }

jib {
    from {
        image = baseImage
    }
    to {
        image = System.getenv("CONTAINER_IMAGE")
    }
}
