import os
import re
from pathlib import Path
from vcxproj2cmake_v3 import convert_vcxproj

def convert_solution(sln_path):
    sln_path = Path(sln_path)
    solution_dir = sln_path.parent
    
    # Parse solution file
    with open(sln_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    
    # Extract project paths
    project_pattern = r'Project\("{[^}]+}\"\)\s*=\s*"([^"]+)",\s*"([^"]+)",\s*"{([^}]+)}"'
    projects = re.findall(project_pattern, content)
    
    # Convert each project
    for name, path, guid in projects:
        if path.endswith(('.vcproj', '.vcxproj')):
            proj_path = solution_dir / path.replace('\\', '/')
            if proj_path.exists():
                print(f"Converting project: {name}")
                convert_vcxproj(proj_path)
    
    # Create main CMakeLists.txt
    with open(solution_dir / 'CMakeLists.txt', 'w') as f:
        f.write('cmake_minimum_required(VERSION 3.16)\n\n')
        f.write(f'project({sln_path.stem})\n\n')
        f.write('set(CMAKE_CXX_STANDARD 20)\n')
        f.write('set(CMAKE_CXX_STANDARD_REQUIRED ON)\n\n')
        
        # Add build configuration options using generator expressions
        f.write('# Build configuration options\n')
        f.write('add_compile_definitions(\n')
        f.write('    $<$<CONFIG:Debug>:_DEBUG>\n')
        f.write('    $<$<NOT:$<CONFIG:Debug>>:NDEBUG>\n')
        f.write(')\n\n')
        
        # Add subdirectories
        f.write('# Add project directories\n')
        for name, path, guid in projects:
            if path.endswith(('.vcproj', '.vcxproj')):
                proj_dir = Path(path).parent
                if proj_dir.name:  # Skip if it's in the root directory
                    f.write(f'add_subdirectory("{proj_dir}")\n')
        f.write('\n')

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert Visual Studio Solution to CMake')
    parser.add_argument('sln_path', help='Path to the .sln file')
    
    args = parser.parse_args()
    convert_solution(args.sln_path)
    print("\nCMake conversion complete!")

if __name__ == '__main__':
    main()