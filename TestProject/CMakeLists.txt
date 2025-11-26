cmake_minimum_required(VERSION 3.20)

project(Testproject)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(CMAKE_EXE_LINKER_FLAGS_TEST "${CMAKE_EXE_LINKER_FLAGS_RELEASE}")
set(CMAKE_SHARED_LINKER_FLAGS_TEST "${CMAKE_SHARED_LINKER_FLAGS_RELEASE}")
set(CMAKE_STATIC_LINKER_FLAGS_TEST "${CMAKE_STATIC_LINKER_FLAGS_RELEASE}")

# Build configuration options
add_compile_definitions(
    $<$<CONFIG:Debug>:_DEBUG>
    $<$<NOT:$<CONFIG:Debug>>:NDEBUG>
)

# Add project directories
add_subdirectory("TestProject")
add_subdirectory("StaticLib1")

# Project name mappings:
# Solution: "TestProject" -> CMake: "TestProject"
# Solution: "StaticLib1" -> CMake: "StaticLib1"
