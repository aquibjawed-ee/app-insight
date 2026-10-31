plugins { kotlin("jvm") version "1.9.22" }
kotlin {
    jvmToolchain(17)
    compilerOptions { jvmTarget.set(JvmTarget.JVM_1_8) }
}
