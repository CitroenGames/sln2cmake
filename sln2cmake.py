import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from vcxproj2cmake import convert_vcxproj

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
        
        # Get all configurations from first project
        first_proj = None
        for name, path, guid in projects:
            if path.endswith(('.vcproj', '.vcxproj')):
                first_proj = solution_dir / path.replace('\\', '/')
                break
                
        if first_proj and first_proj.exists():
            proj_tree = ET.parse(first_proj)
            proj_root = proj_tree.getroot()
            ns = {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'}
            configurations = []
            
            # Check ProjectConfiguration elements
            for proj_config in proj_root.findall('.//ns:ProjectConfiguration', ns):
                config = proj_config.find('ns:Configuration', ns)
                if config is not None and config.text and config.text not in configurations:
                    configurations.append(config.text)
                    
            # Set linker flags for non-standard configurations
            for config in configurations:
                if config not in ['Debug', 'Release']:
                    config_upper = config.upper()
                    f.write(f'set(CMAKE_EXE_LINKER_FLAGS_{config_upper} "${{CMAKE_EXE_LINKER_FLAGS_RELEASE}}")\n')
                    f.write(f'set(CMAKE_SHARED_LINKER_FLAGS_{config_upper} "${{CMAKE_SHARED_LINKER_FLAGS_RELEASE}}")\n')
                    f.write(f'set(CMAKE_STATIC_LINKER_FLAGS_{config_upper} "${{CMAKE_STATIC_LINKER_FLAGS_RELEASE}}")\n')
            f.write('\n')
            
        # Add build configuration options using generator expressions
        f.write('# Build configuration options\n')
        f.write('add_compile_definitions(\n')
        f.write('    $<$<CONFIG:Debug>:_DEBUG>\n')
        f.write('    $<$<NOT:$<CONFIG:Debug>>:NDEBUG>\n')
        f.write(')\n\n')
        
        # Add subdirectories
        f.write('# Add project directories\n')
        added_dirs = set()
        for name, path, guid in projects:
            if path.endswith(('.vcproj', '.vcxproj')):
                proj_dir = Path(path).parent
                if proj_dir.name and proj_dir.name not in added_dirs:  # Skip if it's in the root directory or already added
                    f.write(f'add_subdirectory("{proj_dir.name}")\n')
                    added_dirs.add(proj_dir.name)
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