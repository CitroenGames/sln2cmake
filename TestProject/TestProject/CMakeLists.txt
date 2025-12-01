set(SOURCE_FILES_TestProject
    TestProject.cpp
)
set(HEADER_FILES_TestProject
    forceincludes/forceinclude_debug.h
    forceincludes/forceinclude_release.h
    forceincludes/forceinclude_test.h
)

add_executable(TestProject
    ${SOURCE_FILES_TestProject}
    ${HEADER_FILES_TestProject}
)

target_include_directories(TestProject PRIVATE
    ${CMAKE_SOURCE_DIR}/StaticLib1/
)

target_compile_definitions(TestProject PRIVATE
    _WIN32_WINNT=0x0601
    WINVER=0x0601
    $<$<CONFIG:Debug>:TESTTHING>
    $<$<CONFIG:Release>:TESTTHING;RELEASEPRO>
    $<$<CONFIG:Test>:TESTTHING;TESTCONFIG>
)

# Force includes
target_compile_options(TestProject PRIVATE
    $<$<CONFIG:Debug>:/FIforceincludes/forceinclude_debug.h>
    $<$<CONFIG:Release>:/FIforceincludes/forceinclude_release.h>
    $<$<CONFIG:Test>:/FIforceincludes/forceinclude_test.h>
)

# Compiler options
target_compile_options(TestProject PRIVATE
    /D_WIN32_WINNT=0x0601
    /DWINVER=0x0601
    $<$<CONFIG:Debug>:/W3>
    $<$<CONFIG:Debug>:/std:c++20>
    $<$<CONFIG:Debug>:/permissive->
    $<$<CONFIG:Debug>:/sdl>
    $<$<CONFIG:Release>:/Oi>
    $<$<CONFIG:Release>:/Gy>
    $<$<CONFIG:Release>:/W3>
    $<$<CONFIG:Release>:/std:c++20>
    $<$<CONFIG:Release>:/permissive->
    $<$<CONFIG:Release>:/sdl>
)

# Linker options
target_link_options(TestProject PRIVATE
    $<$<CONFIG:Debug>:/DEBUG>
    $<$<CONFIG:Debug>:/SUBSYSTEM:CONSOLE>
    $<$<CONFIG:Release>:/DEBUG>
    $<$<CONFIG:Release>:/OPT:REF>
    $<$<CONFIG:Release>:/OPT:ICF>
    $<$<CONFIG:Release>:/SUBSYSTEM:CONSOLE>
)

# Output settings

# Project dependencies (CMake targets from this solution)
target_link_libraries(TestProject PRIVATE
    StaticLib1
)
