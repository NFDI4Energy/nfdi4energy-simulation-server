cmake_minimum_required(VERSION 3.10)
project(libsimwrapper)

# Compiler options
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fPIC -fpermissive -w -Ofast")

# Include directories
include_directories(
    /home/mohamed/Desktop/DaceDS/DaceDS4energy-main/CppBaseWrapper/src
    /usr/local/include/librdkafka
    /home/mohamed/Desktop/DaceDS
)

# Sources
file(GLOB_RECURSE SOURCES
    "/home/mohamed/Desktop/DaceDS/DaceDS4energy-main/CppBaseWrapper/src/*.cpp"
)

# Set correct output directory for library
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY "/home/mohamed/Desktop/DaceDS/DaceDS4energy-main/CppBaseWrapper/lib")

# Add library
add_library(simwrapper SHARED ${SOURCES})

# Link directories and libraries
target_link_directories(simwrapper PRIVATE
    /home/mohamed/Desktop/DaceDS/libserdes/src-cpp
    /home/mohamed/Desktop/DaceDS/libserdes/src
)

target_link_libraries(simwrapper
    avrocpp
    serdes++
    pthread
    rdkafka++
    cppkafka
    serdes
    rdkafka
)

