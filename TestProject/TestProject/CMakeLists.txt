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
    ../StaticLib1/
)

target_compile_definitions(TestProject PRIVATE
    $<$<CONFIG:Debug>:TESTTHING>
    $<$<CONFIG:Release>:TESTTHING RELEASEPRO>
    $<$<CONFIG:Test>:TESTTHING TESTCONFIG>
)

target_compile_options(TestProject PRIVATE
    $<$<CONFIG:Debug>:/FIforceincludes/forceinclude_debug.h>
    $<$<CONFIG:Release>:/FIforceincludes/forceinclude_release.h>
    $<$<CONFIG:Test>:/FIforceincludes/forceinclude_test.h>
)

target_link_libraries(TestProject PRIVATE
    StaticLib1
)
