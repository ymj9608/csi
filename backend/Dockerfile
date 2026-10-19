FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
COPY src src
RUN mvn -B package
FROM eclipse-temurin:21-jre
WORKDIR /app
RUN groupadd -r csi && useradd -r -g csi csi
COPY --from=build /build/target/csi-api-0.1.0.jar app.jar
USER csi
ENTRYPOINT ["java","-jar","app.jar"]
