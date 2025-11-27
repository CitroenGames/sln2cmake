import os
import re
import xml.etree.ElementTree as ET
import subprocess
from pathlib import Path
from vcxproj2cmake import convert_vcxproj

def get_cmake_version():
    """Get the installed CMake version and return appropriate minimum version"""
    try:
        result = subprocess.run(['cmake', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            # Extract version from output like "cmake version 4.0.0-rc2"
            version_match = re.search(r'cmake version (\d+)\.(\d+)\.(\d+)', result.stdout)
            if version_match:
                major, minor, patch = map(int, version_match.groups())
                
                # For CMake 4.x, use 3.20 as minimum (good compatibility)
                if major >= 4:
                    return "3.20"
                # For CMake 3.x, use the installed version but at least 3.10
                elif major == 3:
                    if minor >= 20:
                        return "3.20"
                    elif minor >= 16:
                        return "3.16"
                    elif minor >= 10:
                        return f"3.{minor}"
                    else:
                        return "3.10"
                else:
                    return "3.10"
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    
    # Default fallback
    return "3.16"

def get_project_name_from_vcxproj(vcxproj_path):
    """Extract the actual project name from the vcxproj file"""
    try:
        tree = ET.parse(vcxproj_path)
        root = tree.getroot()
        ns = {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'}
        
        # Look for ProjectName in PropertyGroup
        for prop_group in root.findall('.//ns:PropertyGroup', ns):
            project_name = prop_group.find('ns:ProjectName', ns)
            if project_name is not None and project_name.text:
                return project_name.text
        
        # Fallback to filename without extension
        return Path(vcxproj_path).stem
    except:
        return Path(vcxproj_path).stem

def convert_solution(sln_path, target_config=None):
    sln_path = Path(sln_path)
    solution_dir = sln_path.parent
    
    # Parse solution file
    with open(sln_path, 'r', encoding='utf-8-sig') as f:
        content = f.read()
    
    # Extract project paths
    project_pattern = r'Project\("{[^}]+}\"\)\s*=\s*"([^"]+)",\s*"([^"]+)",\s*"{([^}]+)}"'
    projects = re.findall(project_pattern, content)
    
    project_info = []
    
    # Convert each project and collect info
    for sln_name, path, guid in projects:
        if path.endswith(('.vcproj', '.vcxproj')):
            proj_path = solution_dir / path.replace('\\', '/')
            if proj_path.exists():
                # Get the actual project name from the vcxproj file
                actual_name = get_project_name_from_vcxproj(proj_path)
                proj_dir = proj_path.parent
                
                print(f"Converting project: {sln_name}")
                print(f"  Solution name: {sln_name}")
                print(f"  Actual name: {actual_name}")
                print(f"  Path: {proj_path}")
                print(f"  Directory: {proj_dir}")
                
                convert_vcxproj(proj_path, target_config)
                
                project_info.append({
                    'sln_name': sln_name,
                    'actual_name': actual_name,
                    'path': proj_path,
                    'dir': proj_dir,
                    'relative_dir': proj_dir.relative_to(solution_dir) if proj_dir != solution_dir else None
                })
    
    # Get appropriate CMake version
    cmake_min_version = get_cmake_version()
    print(f"Using CMake minimum version: {cmake_min_version}")
    
    # Create main CMakeLists.txt
    with open(solution_dir / 'CMakeLists.txt', 'w') as f:
        f.write(f'cmake_minimum_required(VERSION {cmake_min_version})\n\n')
        
        # Use the solution file name as the project name
        main_project_name = sln_path.stem
            
        f.write(f'project({main_project_name})\n\n')
        f.write('set(CMAKE_CXX_STANDARD 20)\n')
        f.write('set(CMAKE_CXX_STANDARD_REQUIRED ON)\n\n')
        
        # If target_config is specified, add a comment
        if target_config:
            f.write(f'# Converted from configuration: {target_config}\n\n')
        
        # Get all configurations from first project
        if project_info and not target_config:
            first_proj = project_info[0]['path']
            
            if first_proj.exists():
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
        
        # Add build configuration options using generator expressions (only if not target_config)
        if not target_config:
            f.write('# Build configuration options\n')
            f.write('add_compile_definitions(\n')
            f.write('    $<$<CONFIG:Debug>:_DEBUG>\n')
            f.write('    $<$<NOT:$<CONFIG:Debug>>:NDEBUG>\n')
            f.write(')\n\n')
        else:
            # For single config, add the appropriate define directly
            f.write('# Build configuration options\n')
            f.write('add_compile_definitions(\n')
            if target_config == 'Debug':
                f.write('    _DEBUG\n')
            else:
                f.write('    NDEBUG\n')
            f.write(')\n\n')
        
        # Add subdirectories
        f.write('# Add project directories\n')
        added_dirs = set()
        
        for proj in project_info:
            if proj['relative_dir'] and proj['relative_dir'].name not in added_dirs:
                # Convert Path to string with forward slashes for CMake
                relative_dir_str = str(proj['relative_dir']).replace('\\', '/')
                f.write(f'add_subdirectory("{relative_dir_str}")\n')
                added_dirs.add(proj['relative_dir'].name)
            elif not proj['relative_dir']:  # Project is in root directory
                f.write(f'# Project {proj["actual_name"]} is in root directory\n')
        
        f.write('\n')
        
        # Add a comment about project name mappings for clarity
        f.write('# Project name mappings:\n')
        for proj in project_info:
            f.write(f'# Solution: "{proj["sln_name"]}" -> CMake: "{proj["actual_name"]}"\n')

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert Visual Studio Solution to CMake')
    parser.add_argument('sln_path', help='Path to the .sln file')
    parser.add_argument('--config', '-c', dest='config', help='Target configuration to convert (e.g., Debug, Release)')
    
    args = parser.parse_args()
    
    if args.config:
        print(f"Converting with target configuration: {args.config}\n")
    
    convert_solution(args.sln_path, args.config)
    print("\nCMake conversion complete!")

if __name__ == '__main__':
    main()