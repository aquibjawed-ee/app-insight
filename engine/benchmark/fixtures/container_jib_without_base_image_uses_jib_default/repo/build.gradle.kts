plugins { id("com.google.cloud.tools.jib") version "3.4.0" }

jib {
    to {
        image = "acme/app"
    }
}
