FROM maven:3.8.6-openjdk-11 AS basewrapper-builder

WORKDIR /basewrapper
COPY JavaBaseWrapper/ .

# Mirror slow rso-public-grid (repository.sonatype.org) to Maven Central + add JitPack
RUN mkdir -p /root/.m2 && \
    echo '<settings><mirrors><mirror><id>rso-redirect</id><mirrorOf>rso-public-grid</mirrorOf><url>https://repo.maven.apache.org/maven2</url></mirror></mirrors><profiles><profile><id>extra-repos</id><repositories><repository><id>jitpack</id><url>https://jitpack.io</url></repository></repositories></profile></profiles><activeProfiles><activeProfile>extra-repos</activeProfile></activeProfiles></settings>' > /root/.m2/settings.xml

RUN mvn clean install -DskipTests \
    -Dmaven.wagon.http.retryHandler.count=3 \
    -Dmaven.wagon.httpconnectionManager.ttlSeconds=30 \
    -Dmaven.wagon.http.readTimeout=30000 \
    -Dmaven.wagon.http.connectionTimeout=15000

FROM maven:3.8.6-openjdk-11 AS builder

WORKDIR /build

COPY --from=basewrapper-builder /root/.m2/repository/eu/fau/cs7/daceDS/JavaBaseWrapper /root/.m2/repository/eu/fau/cs7/daceDS/JavaBaseWrapper
COPY --from=basewrapper-builder /root/.m2/settings.xml /root/.m2/settings.xml
COPY pom.xml .

RUN mvn dependency:go-offline -B \
    -Dmaven.wagon.http.retryHandler.count=3 \
    -Dmaven.wagon.http.readTimeout=30000 \
    -Dmaven.wagon.http.connectionTimeout=15000 || true

COPY src ./src

RUN mvn clean package -DskipTests \
    -Dmaven.wagon.http.retryHandler.count=3 \
    -Dmaven.wagon.httpconnectionManager.ttlSeconds=30 \
    -Dmaven.wagon.http.readTimeout=30000 \
    -Dmaven.wagon.http.connectionTimeout=15000

FROM eclipse-temurin:11-jre-jammy

RUN useradd -r -s /bin/false simservice

WORKDIR /app

COPY --from=builder /build/target/SimService-0.1-jar-with-dependencies.jar /app/simservice.jar
COPY config.properties /app/config.properties

ENV RABBITMQ_HOST=rabbitmq
ENV REDIS_HOST=redis

RUN chown -R simservice:simservice /app

USER simservice

CMD ["java", "-jar", "/app/simservice.jar"]
