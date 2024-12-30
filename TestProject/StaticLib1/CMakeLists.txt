# Project settings
set(SOURCE_FILES_StaticLib1 pch.cpp StaticLib1.cpp)
set(HEADER_FILES_StaticLib1 framework.h pch.h)
add_library(StaticLib1 STATIC
    ${SOURCE_FILES_StaticLib1}
    ${HEADER_FILES_StaticLib1}
)
target_compile_definitions(StaticLib1 PRIVATE -D_DEBUG -D_LIB -DNDEBUG)
