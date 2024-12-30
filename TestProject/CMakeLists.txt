cmake_minimum_required(VERSION 3.16)

project(TestProject)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build configuration options
add_compile_definitions(
    $<$<CONFIG:Debug>:_DEBUG>
    $<$<NOT:$<CONFIG:Debug>>:NDEBUG>
)

# Add project directories
add_subdirectory("TestProject")
add_subdirectory("StaticLib1")

