rootProject.name = "svc"
include("contract")
project(":contract").projectDir = file("contract")
project(":contract").buildFileName = "contract.gradle.kts"
include("functional")
project(":functional").projectDir = file("functional")
project(":functional").buildFileName = "functional.gradle.kts"
