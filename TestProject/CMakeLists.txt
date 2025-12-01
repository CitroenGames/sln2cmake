cmake_minimum_required(VERSION 3.20)

project(TestProject)

# C++ Standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
# Note: Some projects override this standard (see individual CMakeLists.txt)

set(CMAKE_EXE_LINKER_FLAGS_TEST "${CMAKE_EXE_LINKER_FLAGS_RELEASE}")
set(CMAKE_SHARED_LINKER_FLAGS_TEST "${CMAKE_SHARED_LINKER_FLAGS_RELEASE}")
set(CMAKE_STATIC_LINKER_FLAGS_TEST "${CMAKE_STATIC_LINKER_FLAGS_RELEASE}")

# Build configuration options
add_compile_definitions(
    $<$<CONFIG:Debug>:_DEBUG>
    $<$<NOT:$<CONFIG:Debug>>:NDEBUG>
)

# Add project directories
# Libraries (built first)
add_subdirectory("StaticLib1")

# Executables
add_subdirectory("TestProject")

# Project name mappings:
# Solution: "TestProject" -> CMake: "TestProject"
# Solution: "StaticLib1" -> CMake: "StaticLib1" (C++14) [library]

# Note: Internal project dependencies are linked using target_link_libraries
# Solution contains 2 CMake targets that can be linked by name
