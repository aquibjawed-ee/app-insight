plugins { kotlin("jvm") version "1.9.24" }
dependencies {
    implementation("io.ktor:ktor-server-core:2.3.0")
    implementation("io.ktor:ktor-client-cio:2.3.0")
    implementation("org.jetbrains.exposed:exposed-core:0.50.0")
    implementation("org.postgresql:postgresql:42.7.3")
    implementation("io.lettuce:lettuce-core:6.3.0")
    // implementation("org.mongodb:mongodb-driver-sync:5.0.0")
    testImplementation("org.testcontainers:postgresql:1.19.0")
}
