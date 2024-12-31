import os
import xml.etree.ElementTree as ET
from pathlib import Path

def _get_configuration_settings(compile_settings, settings, ns):
    """Extract configuration-specific settings from compile settings"""
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
            
    # Get configuration from condition
    config = None
    if 'Condition' in compile_settings.attrib:
        condition = compile_settings.attrib['Condition']
        if "'$(Configuration)'=='" in condition:
            config = condition.split("'")[3]
    
    # Get configuration-specific preprocessor definitions
    if config:
        config_defs = compile_settings.find(f'ns:{config}PreprocessorDefinitions', ns)
        if config_defs is not None and config_defs.text:
            defs = [d.strip() for d in config_defs.text.split(';') if d.strip() and d != f'%({config}PreprocessorDefinitions)']
            if defs:
                if 'config_defines' not in settings:
                    settings['config_defines'] = {}
                settings['config_defines'][config] = defs
    
    # Get force includes
    force_inc = compile_settings.find('ns:ForcedIncludeFiles', ns)
    if force_inc is not None and force_inc.text:
        includes = [i.strip() for i in force_inc.text.split(';') if i.strip() and i != '%(ForcedIncludeFiles)']
        if includes:
            includes = [os.path.relpath(i, '.').replace('\\', '/') for i in includes]
            settings['force_includes'] = includes

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

def convert_vcxproj(vcxproj_path):
    tree = ET.parse(vcxproj_path)
    root = tree.getroot()
    ns = {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'}
    
    # Initialize CMake content
    cmake_content = []
    cmake_content.append('# Project settings')
    
    # Get configurations
    configurations = get_configurations(root, ns)
    if configurations:
        cmake_content.append('set(CMAKE_CONFIGURATION_TYPES')
        for config in configurations:
            cmake_content.append(f'    "{config}"')
        cmake_content.append('    CACHE STRING "" FORCE)')
        
        cmake_content.append('')
    
    # Get project name
    project_name = Path(vcxproj_path).stem
    
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
        cmake_content.append(f'set(SOURCE_FILES_{project_name} {" ".join(sources)})')
    if headers:
        cmake_content.append(f'set(HEADER_FILES_{project_name} {" ".join(headers)})')
    
    # Determine if it's a library
    is_lib = False
    config_type = root.find('.//ns:ConfigurationType', ns)
    if config_type is not None and 'StaticLibrary' in config_type.text:
        is_lib = True
    
    # Add target
    if is_lib:
        cmake_content.append(f'add_library({project_name} STATIC')
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
        
        if compile_settings is not None and "'$(Configuration)|$(Platform)'=='" in condition:
            config = condition.split("'")[3].split('|')[0]
            if config not in config_settings:
                config_settings[config] = {}
            _get_configuration_settings(compile_settings, config_settings[config], ns)
    
    # Write configuration-specific settings
    all_include_dirs = set()
    config_defines = {}
    
    # Collect all unique settings and organize defines by configuration
    for config, settings in config_settings.items():
        if settings.get('include_dirs'):
            all_include_dirs.update(settings['include_dirs'])
        
        # Collect defines for this configuration
        if settings:
            defines = set()
            if settings.get('defines'):
                defines.update(settings['defines'])
            if settings.get('config_defines', {}).get(config):
                defines.update(settings['config_defines'][config])
            if defines:
                config_defines[config] = defines
    
    # Write include directories
    if all_include_dirs:
        cmake_content.append(f'target_include_directories({project_name} PRIVATE {" ".join(all_include_dirs)})')
    
    # Write configuration-specific defines using generator expressions
    if config_defines:
        defines_expr = []
        for config, defines in config_defines.items():
            if defines:
                defines_expr.append(f'$<$<CONFIG:{config}>:{" ".join([f"-D{d}" for d in defines])}>')
        if defines_expr:
            cmake_content.append(f'target_compile_definitions({project_name} PRIVATE {" ".join(defines_expr)})')
    
    # Write force includes using generator expressions
    force_includes = []
    for config, settings in config_settings.items():
        if settings.get('force_includes'):
            force_includes.extend([f'$<$<CONFIG:{config}>:/FI{i}>' for i in settings['force_includes']])
    
    if force_includes:
        cmake_content.append(f'target_compile_options({project_name} PRIVATE {" ".join(force_includes)})')
    
    # Get project references
    for ref in root.findall('.//ns:ProjectReference', ns):
        if 'Include' in ref.attrib:
            dep_path = Path(ref.attrib['Include'])
            dep_name = dep_path.stem
            cmake_content.append(f'target_link_libraries({project_name} PRIVATE {dep_name})')
    
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