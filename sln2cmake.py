import os
import re
import xml.etree.ElementTree as ET
import subprocess
from pathlib import Path
from collections import defaultdict
from vcxproj2cmake import convert_vcxproj, get_cpp_standard, write_cmake_file, write_combined_cmake_file

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

def sanitize_cmake_name(name):
    """Sanitize a project name for use in CMake (must match vcxproj2cmake logic)"""
    return name.replace('-', '_').replace(' ', '_').replace('(', '_').replace(')', '_')

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
    cpp_standards = []
    
    # Group projects by directory to detect multiple projects in same dir
    projects_by_dir = defaultdict(list)
    
    # ============================================================
    # PHASE 1: Collect ALL project names first
    # This allows us to identify internal dependencies vs external libraries
    # ============================================================
    # Dictionary mapping lowercase sanitized name -> proper-case sanitized name
    # The proper case comes from the vcxproj ProjectName element
    all_solution_projects = {}  # lowercase_name -> ProperCaseName
    project_name_mapping = {}  # Map from original name -> sanitized name
    
    print("="*60)
    print("PHASE 1: Collecting all projects in solution...")
    print("="*60)
    
    for sln_name, path, guid in projects:
        if path.endswith(('.vcproj', '.vcxproj')):
            proj_path = solution_dir / path.replace('\\', '/')
            if proj_path.exists():
                # Get the actual project name from the vcxproj file
                actual_name = get_project_name_from_vcxproj(proj_path)
                sanitized_name = sanitize_cmake_name(actual_name)
                
                # Store with lowercase key -> proper case value
                # The vcxproj ProjectName is the authoritative source for casing
                all_solution_projects[sanitized_name.lower()] = sanitized_name
                project_name_mapping[actual_name] = sanitized_name
                
                # Also add the solution name as an alias pointing to the same proper-case name
                sanitized_sln_name = sanitize_cmake_name(sln_name)
                # Only add if not already present (vcxproj name takes precedence)
                if sanitized_sln_name.lower() not in all_solution_projects:
                    all_solution_projects[sanitized_sln_name.lower()] = sanitized_name
                project_name_mapping[sln_name] = sanitized_sln_name
                
                print(f"  Found project: {actual_name} -> CMake target: {sanitized_name}")
    
    print(f"\nTotal projects found: {len(all_solution_projects)}")
    print("="*60 + "\n")
    
    # ============================================================
    # PHASE 2: Collect detailed project info
    # ============================================================
    print("PHASE 2: Analyzing project configurations...")
    print("="*60)
    
    for sln_name, path, guid in projects:
        if path.endswith(('.vcproj', '.vcxproj')):
            proj_path = solution_dir / path.replace('\\', '/')
            if proj_path.exists():
                # Get the actual project name from the vcxproj file
                actual_name = get_project_name_from_vcxproj(proj_path)
                proj_dir = proj_path.parent
                
                # Get C++ standard for this project
                cpp_std = get_cpp_standard(proj_path, target_config)
                cpp_standards.append(cpp_std)
                
                info = {
                    'sln_name': sln_name,
                    'actual_name': actual_name,
                    'path': proj_path,
                    'dir': proj_dir,
                    'relative_dir': proj_dir.relative_to(solution_dir) if proj_dir != solution_dir else None,
                    'cpp_standard': cpp_std
                }
                
                project_info.append(info)
                projects_by_dir[str(proj_dir)].append(info)
    
    # Detect directories with multiple projects
    multi_project_dirs = {dir_path: projs for dir_path, projs in projects_by_dir.items() if len(projs) > 1}
    
    if multi_project_dirs:
        print("\n" + "="*60)
        print("DETECTED MULTIPLE PROJECTS IN SAME DIRECTORY:")
        for dir_path, projs in multi_project_dirs.items():
            print(f"  {dir_path}:")
            for p in projs:
                print(f"    - {p['actual_name']} ({p['path'].name})")
        print("="*60 + "\n")
    
    # ============================================================
    # PHASE 3: Convert each project, passing the solution project set
    # ============================================================
    print("\nPHASE 3: Converting projects...")
    print("="*60)
    
    processed_dirs = set()
    
    for sln_name, path, guid in projects:
        if path.endswith(('.vcproj', '.vcxproj')):
            proj_path = solution_dir / path.replace('\\', '/')
            if proj_path.exists():
                proj_dir = str(proj_path.parent)
                
                # Check if this directory has multiple projects
                if proj_dir in multi_project_dirs:
                    # Only process once per directory
                    if proj_dir in processed_dirs:
                        continue
                    processed_dirs.add(proj_dir)
                    
                    # Convert all projects in this directory
                    dir_projects = multi_project_dirs[proj_dir]
                    print(f"\nConverting {len(dir_projects)} projects in {proj_dir}:")
                    
                    cmake_results = []
                    for proj in dir_projects:
                        print(f"  Converting: {proj['actual_name']}")
                        print(f"    Solution name: {proj['sln_name']}")
                        print(f"    C++ Standard: {proj['cpp_standard']}")
                        print(f"    Path: {proj['path']}")
                        
                        # Pass the set of all solution projects for dependency resolution
                        result = convert_vcxproj(
                            proj['path'], 
                            target_config, 
                            proj['cpp_standard'],
                            solution_projects=all_solution_projects
                        )
                        result['proj_info'] = proj
                        cmake_results.append(result)
                    
                    # Build a map of project names in this directory for dependency checking
                    same_dir_projects = {r['project_name']: r for r in cmake_results}
                    
                    # Write combined CMakeLists.txt
                    write_combined_cmake_file(Path(proj_dir), cmake_results, same_dir_projects)
                    
                else:
                    # Single project in directory - use original logic
                    actual_name = get_project_name_from_vcxproj(proj_path)
                    cpp_std = get_cpp_standard(proj_path, target_config)
                    
                    print(f"\nConverting project: {sln_name}")
                    print(f"  Solution name: {sln_name}")
                    print(f"  Actual name: {actual_name}")
                    print(f"  C++ Standard: {cpp_std}")
                    print(f"  Path: {proj_path}")
                    print(f"  Directory: {proj_path.parent}")
                    
                    # Pass the set of all solution projects for dependency resolution
                    result = convert_vcxproj(
                        proj_path, 
                        target_config, 
                        cpp_std,
                        solution_projects=all_solution_projects
                    )
                    write_cmake_file(proj_path, result)
    
    # Determine if all projects use the same C++ standard
    if not cpp_standards:
        print("No projects found!")
        return
        
    unique_standards = set(cpp_standards)
    if len(unique_standards) == 1:
        common_cpp_standard = cpp_standards[0]
        use_common_standard = True
        print(f"\nAll projects use C++ standard: {common_cpp_standard}")
    else:
        common_cpp_standard = max(cpp_standards)  # Use highest standard as default
        use_common_standard = False
        print(f"\nProjects use different C++ standards: {unique_standards}")
        print(f"Setting default to: {common_cpp_standard}")
    
    # Get appropriate CMake version
    cmake_min_version = get_cmake_version()
    print(f"Using CMake minimum version: {cmake_min_version}")
    
    # Create main CMakeLists.txt
    with open(solution_dir / 'CMakeLists.txt', 'w') as f:
        f.write(f'cmake_minimum_required(VERSION {cmake_min_version})\n\n')
        
        # Use the solution file name as the project name
        main_project_name = sln_path.stem
            
        f.write(f'project({main_project_name})\n\n')
        
        # Set C++ standard at solution level
        f.write(f'# C++ Standard\n')
        f.write(f'set(CMAKE_CXX_STANDARD {common_cpp_standard})\n')
        f.write('set(CMAKE_CXX_STANDARD_REQUIRED ON)\n')
        
        if not use_common_standard:
            f.write('# Note: Some projects override this standard (see individual CMakeLists.txt)\n')
        
        f.write('\n')
        
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
        
        # First pass: identify libraries vs executables
        lib_projects = []
        exe_projects = []
        
        for proj in project_info:
            try:
                proj_tree = ET.parse(proj['path'])
                proj_root = proj_tree.getroot()
                ns_check = {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'}
                
                # Check if it's a library
                is_library = False
                for prop_group in proj_root.findall('.//ns:PropertyGroup', ns_check):
                    config_type = prop_group.find('ns:ConfigurationType', ns_check)
                    if config_type is not None and config_type.text:
                        if 'Library' in config_type.text:
                            is_library = True
                            break
                
                proj['is_library'] = is_library
                
                if is_library:
                    lib_projects.append(proj)
                else:
                    exe_projects.append(proj)
            except:
                # If we can't parse, assume it's an executable
                proj['is_library'] = False
                exe_projects.append(proj)
        
        # Add libraries first (they need to be built before executables that depend on them)
        f.write('# Libraries (built first)\n')
        for proj in lib_projects:
            if proj['relative_dir'] and str(proj['relative_dir']) not in added_dirs:
                relative_dir_str = str(proj['relative_dir']).replace('\\', '/')
                f.write(f'add_subdirectory("{relative_dir_str}")\n')
                added_dirs.add(str(proj['relative_dir']))
            elif not proj['relative_dir']:
                f.write(f'# Library {proj["actual_name"]} is in root directory\n')
        
        # Then add executables
        f.write('\n# Executables\n')
        for proj in exe_projects:
            if proj['relative_dir'] and str(proj['relative_dir']) not in added_dirs:
                relative_dir_str = str(proj['relative_dir']).replace('\\', '/')
                f.write(f'add_subdirectory("{relative_dir_str}")\n')
                added_dirs.add(str(proj['relative_dir']))
            elif not proj['relative_dir']:
                f.write(f'# Executable {proj["actual_name"]} is in root directory\n')
        
        f.write('\n')
        
        # Add a comment about project name mappings for clarity
        f.write('# Project name mappings:\n')
        for proj in project_info:
            cpp_note = f" (C++{proj['cpp_standard']})" if not use_common_standard and proj['cpp_standard'] != common_cpp_standard else ""
            is_lib_note = " [library]" if proj.get('is_library') else ""
            f.write(f'# Solution: "{proj["sln_name"]}" -> CMake: "{sanitize_cmake_name(proj["actual_name"])}"{cpp_note}{is_lib_note}\n')
        
        # Add note about multi-project directories
        if multi_project_dirs:
            f.write('\n# Note: The following directories contain multiple projects in a single CMakeLists.txt:\n')
            for dir_path, projs in multi_project_dirs.items():
                rel_dir = Path(dir_path).relative_to(solution_dir) if Path(dir_path) != solution_dir else "."
                proj_names = ", ".join(p['actual_name'] for p in projs)
                f.write(f'#   {rel_dir}: {proj_names}\n')
        
        # Add note about internal project linking
        f.write('\n# Note: Internal project dependencies are linked using target_link_libraries\n')
        f.write(f'# Solution contains {len(all_solution_projects)} CMake targets that can be linked by name\n')

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
