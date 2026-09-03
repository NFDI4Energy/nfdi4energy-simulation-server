# Multi-stage build for SUMO Wrapper with CppBaseWrapper
FROM ubuntu:22.04 AS builder

# Avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive
ENV SUMO_HOME=/opt/sumo

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    pkg-config \
    libssl-dev \
    zlib1g-dev \
    libboost-all-dev \
    python3 \
    python3-pip \
    libtool \
    autoconf \
    automake \
    # libserdes dependencies
    libjansson-dev \
    libavro-dev \
    libcurl4-openssl-dev \
    # SUMO dependencies
    libxerces-c-dev \
    libfox-1.6-dev \
    libgdal-dev \
    libproj-dev \
    libgl2ps-dev \
    libfmt-dev \
    swig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# ============================================
# Stage 1: Build librdkafka
# ============================================
RUN git clone https://github.com/confluentinc/librdkafka.git && \
    cd librdkafka && \
    git checkout v2.3.0 && \
    ./configure --prefix=/usr/local && \
    make -j$(nproc) && \
    make install && \
    ldconfig

# ============================================
# Stage 2: Build Avro C++ 1.12.0
# ============================================
RUN wget https://archive.apache.org/dist/avro/avro-1.12.0/cpp/avro-cpp-1.12.0.tar.gz && \
    tar -xzf avro-cpp-1.12.0.tar.gz && \
    cd avro-cpp-1.12.0 && \
    rm -rf build && \
    mkdir -p build && cd build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_BUILD_TYPE=Release -DCMAKE_POSITION_INDEPENDENT_CODE=ON && \
    make -j$(nproc) && \
    make install && \
    ldconfig

# ============================================
# Stage 3: Build fmt (required for SUMO with PIC)
# ============================================
RUN wget https://github.com/fmtlib/fmt/archive/refs/tags/10.2.1.tar.gz && \
    tar -xzf 10.2.1.tar.gz && \
    cd fmt-10.2.1 && \
    mkdir -p build && cd build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_BUILD_TYPE=Release -DCMAKE_POSITION_INDEPENDENT_CODE=ON -DFMT_TEST=OFF && \
    make -j$(nproc) && \
    make install && \
    ldconfig

# ============================================
# Stage 4: Install SUMO v1.21.0
# ============================================
#RUN wget https://github.com/eclipse/sumo/archive/refs/tags/v1_21_0.tar.gz && \
#    tar -xzf v1_21_0.tar.gz && \
#    cd sumo-1_21_0 && \
#    rm -rf build && \
#    mkdir -p build && cd build && \
#    cmake .. -DCMAKE_INSTALL_PREFIX=/opt/sumo -DCMAKE_BUILD_TYPE=Release -DCMAKE_POSITION_INDEPENDENT_CODE=ON && \
 #   make -j$(nproc) && \
 #   make install

# ============================================
# Stage 4: Install SUMO v1.27.1
# ============================================
RUN wget https://github.com/eclipse-sumo/sumo/archive/refs/tags/v1_27_1.tar.gz && \
    tar -xzf v1_27_1.tar.gz && \
    cd sumo-1_27_1 && \
    rm -rf build && \
    mkdir -p build && cd build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/opt/sumo -DCMAKE_BUILD_TYPE=Release -DCMAKE_POSITION_INDEPENDENT_CODE=ON && \
    make -j$(nproc) && \
    make install

# Keep local source layers after SUMO so wrapper edits reuse the expensive build.

# ============================================
# Stage 5: Build libserdes
# ============================================
COPY CppBaseWrapper/libserdes /build/libserdes
RUN cd /build/libserdes && \
    make clean >/dev/null 2>&1 || true
RUN cd /build/libserdes && \
    rm -f config.cache config.h Makefile.config && \
    chmod +x configure && \
    ./configure --prefix=/usr/local --CFLAGS="-fPIC" --CXXFLAGS="-fPIC" && \
    sed -i 's/--std=c++11/--std=c++17/g' Makefile.config && \
    make -j$(nproc) && \
    make install && \
    ldconfig

# ============================================
# Stage 6: Build cppkafka
# ============================================
COPY CppBaseWrapper/cppkafka /build/cppkafka

RUN echo "=== CMakeLists.txt ===" && \
    grep -n "add_subdirectory" /build/cppkafka/CMakeLists.txt && \
    echo "=== Disable tests ===" && \
    grep -n "CPPKAFKA_DISABLE_TESTS" /build/cppkafka/CMakeLists.txt

RUN cd /build/cppkafka && \
    rm -rf build && \
    mkdir build && cd build && \
    cmake .. \
      -DCMAKE_INSTALL_PREFIX=/usr/local \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
      -DCPPKAFKA_DISABLE_TESTS=ON && \
    make -j$(nproc) && \
    make install && \
    ldconfig

# ============================================
# Stage 7: Build pugixml
# ============================================
COPY CppBaseWrapper/pugixml /build/pugixml
RUN cd /build/pugixml && \
    rm -rf build && \
    mkdir -p build && cd build && \
    cmake .. -DCMAKE_INSTALL_PREFIX=/usr/local -DCMAKE_BUILD_TYPE=Release -DCMAKE_POSITION_INDEPENDENT_CODE=ON && \
    make -j$(nproc) && \
    make install && \
    ldconfig

# Add SUMO to PATH
ENV PATH="${SUMO_HOME}/bin:${PATH}"
ENV LD_LIBRARY_PATH="/usr/local/lib:${SUMO_HOME}/lib"

# ============================================
# Stage 8: Build CppBaseWrapper
# ============================================
WORKDIR /build/CppBaseWrapper
COPY CppBaseWrapper/ .

# Use Docker-specific Makefile
RUN cp Makefile.docker Makefile

# Build CppBaseWrapper
RUN make clean && make -j$(nproc)

# ============================================
# Stage 9: Build SumoWrapper
# ============================================
WORKDIR /build/SumoWrapper
COPY SumoWrapper/ .

# Use Docker-specific Makefile
RUN cp Makefile.docker Makefile

# Build SumoWrapper
RUN make clean && make -j$(nproc)

# ============================================
# Runtime Stage
# ============================================
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV SUMO_HOME=/opt/sumo
ENV PATH="${SUMO_HOME}/bin:${PATH}"
ENV LD_LIBRARY_PATH="/usr/local/lib:${SUMO_HOME}/lib"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libboost-filesystem1.74.0 \
    libboost-iostreams1.74.0 \
    libboost-program-options1.74.0 \
    libboost-thread1.74.0 \
    libxerces-c3.2 \
    libfox-1.6-0 \
    libgdal30 \
    libproj22 \
    libgl2ps1.4 \
    libfmt8 \
    libjansson4 \
    libavro23 \
    libcurl4 \
    libssl3 \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Copy SUMO from builder
COPY --from=builder /opt/sumo /opt/sumo

# Copy all built libraries
COPY --from=builder /usr/local/lib/librdkafka*.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/libavrocpp*.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/libserdes*.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/libcppkafka*.so* /usr/local/lib/

# Copy CppBaseWrapper library
COPY --from=builder /build/CppBaseWrapper/lib/libsimwrapper.so /usr/local/lib/

# Copy SumoWrapper binary
COPY --from=builder /build/SumoWrapper/SumoWrapper /app/

# Copy required resource files (config.properties and default SUMO config template)
COPY --from=builder /build/SumoWrapper/resource/ /app/resource/

# Update library cache
RUN ldconfig

WORKDIR /app

# Environment variables for Kafka (will be overridden by Kubernetes)
ENV KAFKA_BROKER=broker:29092
ENV SCHEMA_REGISTRY=http://schema-registry:8081
ENV SCENARIO_ID=""
ENV INSTANCE_ID=""

# SumoWrapper requires two arguments: ScenarioID and SimulatorID
# These will be provided by Kubernetes Job via CMD override
# If running standalone for testing, provide: docker run image ScenarioID SimulatorID
ENTRYPOINT ["/app/SumoWrapper"]
