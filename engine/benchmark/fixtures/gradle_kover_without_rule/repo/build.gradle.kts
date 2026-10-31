plugins {
  kotlin("jvm") version "1.9.22"
  id("org.jetbrains.kotlinx.kover") version "0.7.5"
}
kotlin { jvmToolchain(17) }
tasks.test { useJUnitPlatform() }
