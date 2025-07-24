import os
import xml.etree.ElementTree as ET
from pathlib import Path

def _get_configuration_settings(compile_settings, link_settings, settings, ns, config_name):
    """Extract configuration-specific settings from compile and link settings"""
    # Get include directories
    inc_dirs = compile_settings.find('ns:AdditionalIncludeDirectories', ns)
    if inc_dirs is not None and inc_dirs.text:
        dirs = [d.strip() for d in inc_dirs.text.split(';') if d.strip() and d != '%(AdditionalIncludeDirectories)']
        if dirs:
            dirs = [d.replace('$(SolutionDir)', '../').replace('\\', '/') for d in dirs]
            settings['include_dirs'] = dirs
    
    # Get preprocessor definitions
    defines = compile_settings.find('ns:PreprocessorDefinitions', ns)
    if defines is not None and defines.text:
        defs = [d.strip() for d in defines.text.split(';') if d.strip() and d != '%(PreprocessorDefinitions)']
        if defs:
            settings['defines'] = defs
    
    # Get force includes
    force_inc = compile_settings.find('ns:ForcedIncludeFiles', ns)
    if force_inc is not None and force_inc.text:
        includes = [i.strip() for i in force_inc.text.split(';') if i.strip() and i != '%(ForcedIncludeFiles)']
        if includes:
            includes = [i.replace('\\', '/') for i in includes]
            settings['force_includes'] = includes
    
    # Get additional library dependencies from link settings
    if link_settings is not None:
        additional_deps = link_settings.find('ns:AdditionalDependencies', ns)
        if additional_deps is not None and additional_deps.text:
            libs = [lib.strip() for lib in additional_deps.text.split(';') 
                   if lib.strip() and lib.strip() not in ['%(AdditionalDependencies)', '']]
            if libs:
                settings['libraries'] = libs

def get_configurations(root, ns):
    """Extract all configurations from the project"""
    configs = set()
    # Check ProjectConfiguration elements
    for proj_config in root.findall('.//ns:ProjectConfiguration', ns):
        config = proj_config.find('ns:Configuration', ns)
        if config is not None and config.text:
            configs.add(config.text)
            
    # Also check ItemDefinitionGroup for any additional configs
    for item_def in root.findall('.//ns:ItemDefinitionGroup', ns):
        condition = item_def.get('Condition', '')
        if "'$(Configuration)|$(Platform)'=='" in condition:
            config = condition.split("'")[3].split('|')[0]
            configs.add(config)
            
    return sorted(list(configs))

def get_project_type(root, ns, config_name='Debug'):
    """Determine if project is executable or library"""
    # Look for ConfigurationType in PropertyGroup elements
    for prop_group in root.findall('.//ns:PropertyGroup', ns):
        condition = prop_group.get('Condition', '')
        if f"'{config_name}|" in condition or 'Label="Configuration"' in prop_group.attrib:
            config_type = prop_group.find('ns:ConfigurationType', ns)
            if config_type is not None and config_type.text:
                return config_type.text
    
    # Default to Application if not found
    return 'Application'

def get_project_name(root, ns, fallback_name):
    """Get the project name from PropertyGroup, with fallback"""
    # Look for ProjectName in PropertyGroup
    for prop_group in root.findall('.//ns:PropertyGroup', ns):
        project_name = prop_group.find('ns:ProjectName', ns)
        if project_name is not None and project_name.text:
            return project_name.text
    
    # Fallback to the provided name
    return fallback_name

def convert_vcxproj(vcxproj_path):
    tree = ET.parse(vcxproj_path)
    root = tree.getroot()
    ns = {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'}
    
    # Initialize CMake content
    cmake_content = []
    
    # Get project name (prefer ProjectName from PropertyGroup, fallback to filename)
    fallback_name = Path(vcxproj_path).stem
    project_name = get_project_name(root, ns, fallback_name)
    
    # Sanitize project name for CMake (replace invalid characters)
    project_name = project_name.replace('-', '_').replace(' ', '_')
    
    print(f"  Using project name: {project_name}")
    
    # Get configurations
    configurations = get_configurations(root, ns)
    
    # Get source files
    sources = []
    headers = []
    for item_group in root.findall('.//ns:ClCompile', ns):
        if 'Include' in item_group.attrib:
            sources.append(item_group.attrib['Include'].replace('\\', '/'))
    
    for item_group in root.findall('.//ns:ClInclude', ns):
        if 'Include' in item_group.attrib:
            headers.append(item_group.attrib['Include'].replace('\\', '/'))
    
    # Write source files
    if sources:
        cmake_content.append(f'set(SOURCE_FILES_{project_name}')
        for source in sources:
            cmake_content.append(f'    {source}')
        cmake_content.append(')')
    
    if headers:
        cmake_content.append(f'set(HEADER_FILES_{project_name}')
        for header in headers:
            cmake_content.append(f'    {header}')
        cmake_content.append(')')
    
    # Determine project type
    project_type = get_project_type(root, ns)
    is_lib = 'StaticLibrary' in project_type or 'DynamicLibrary' in project_type
    
    # Add target
    cmake_content.append('')
    if is_lib:
        lib_type = 'STATIC' if 'StaticLibrary' in project_type else 'SHARED'
        cmake_content.append(f'add_library({project_name} {lib_type}')
    else:
        cmake_content.append(f'add_executable({project_name}')
    
    if sources:
        cmake_content.append(f'    ${{{f"SOURCE_FILES_{project_name}"}}}')
    if headers:
        cmake_content.append(f'    ${{{f"HEADER_FILES_{project_name}"}}}')
    cmake_content.append(')')
    
    # Process configurations
    config_settings = {}
    
    for item_def in root.findall('.//ns:ItemDefinitionGroup', ns):
        condition = item_def.get('Condition', '')
        compile_settings = item_def.find('.//ns:ClCompile', ns)
        link_settings = item_def.find('.//ns:Link', ns)
        
        if compile_settings is not None and "'$(Configuration)|$(Platform)'=='" in condition:
            config_platform = condition.split("'")[3]
            config = config_platform.split('|')[0]
            platform = config_platform.split('|')[1]
            
            if config not in config_settings:
                config_settings[config] = {}
            
            _get_configuration_settings(compile_settings, link_settings, config_settings[config], ns, config)
    
    # Write configuration-specific settings
    all_include_dirs = set()
    all_defines = {}
    all_force_includes = {}
    all_libraries = set()
    
    # Collect all settings
    for config, settings in config_settings.items():
        if settings.get('include_dirs'):
            all_include_dirs.update(settings['include_dirs'])
        
        if settings.get('defines'):
            all_defines[config] = settings['defines']
            
        if settings.get('force_includes'):
            all_force_includes[config] = settings['force_includes']
            
        if settings.get('libraries'):
            all_libraries.update(settings['libraries'])
    
    # Write include directories (common to all configs)
    if all_include_dirs:
        cmake_content.append('')
        cmake_content.append(f'target_include_directories({project_name} PRIVATE')
        for inc_dir in sorted(all_include_dirs):
            cmake_content.append(f'    {inc_dir}')
        cmake_content.append(')')
    
    # Write configuration-specific defines
    if all_defines:
        cmake_content.append('')
        cmake_content.append(f'target_compile_definitions({project_name} PRIVATE')
        for config in sorted(all_defines.keys()):
            defines = all_defines[config]
            define_str = ' '.join(defines)
            cmake_content.append(f'    $<$<CONFIG:{config}>:{define_str}>')
        cmake_content.append(')')
    
    # Write force includes
    if all_force_includes:
        cmake_content.append('')
        cmake_content.append('# Force includes')
        cmake_content.append(f'target_compile_options({project_name} PRIVATE')
        for config in sorted(all_force_includes.keys()):
            includes = all_force_includes[config]
            for include in includes:
                cmake_content.append(f'    $<$<CONFIG:{config}>:/FI{include}>')
        cmake_content.append(')')
    
    # Write libraries
    if all_libraries:
        cmake_content.append('')
        cmake_content.append(f'target_link_libraries({project_name} PRIVATE')
        for lib in sorted(all_libraries):
            # Convert .lib to just the library name for CMake
            if lib.endswith('.lib'):
                lib_name = lib[:-4]  # Remove .lib extension
            else:
                lib_name = lib
            cmake_content.append(f'    {lib_name}')
        cmake_content.append(')')
    
    # Get project references
    project_refs = []
    for ref in root.findall('.//ns:ProjectReference', ns):
        if 'Include' in ref.attrib:
            dep_path = Path(ref.attrib['Include'])
            dep_name = dep_path.stem
            project_refs.append(dep_name)
    
    if project_refs:
        cmake_content.append('')
        cmake_content.append('# Project dependencies')
        cmake_content.append(f'target_link_libraries({project_name} PRIVATE')
        for ref in project_refs:
            cmake_content.append(f'    {ref}')
        cmake_content.append(')')
    
    # Write CMakeLists.txt
    output_dir = Path(vcxproj_path).parent
    with open(output_dir / 'CMakeLists.txt', 'w') as f:
        f.write('\n'.join(cmake_content))
        f.write('\n')

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert Visual Studio Project to CMake')
    parser.add_argument('vcxproj_path', help='Path to the .vcxproj file')
    
    args = parser.parse_args()
    convert_vcxproj(args.vcxproj_path)

if __name__ == '__main__':
    main()