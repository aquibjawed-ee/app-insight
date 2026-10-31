plugins { id("org.springframework.boot") version "3.2.0"
 kotlin("jvm") version "1.9.24" }
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-mongodb")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
