#include <iostream>

#include "framework.h"

int main()
{
#ifdef TESTTHING && STATICLIB_TEST
    std::cout << FORCEINCLUDE;
#endif

    framework obj;
    obj.fnStaticLib1();

}