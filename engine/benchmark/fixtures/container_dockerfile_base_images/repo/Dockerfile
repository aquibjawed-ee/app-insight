FROM maven:3.9-eclipse-temurin-17 AS build
RUN mvn -q package
FROM eclipse-temurin:17-jre
COPY --from=build /app.jar /app.jar
FROM build AS extra
