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
            
    # Get configuration-specific preprocessor definitions
    config_defines = {
        'Debug': 'DebugPreprocessorDefinitions',
        'Release': 'ReleasePreprocessorDefinitions',
        'Profile': 'ProfilePreprocessorDefinitions'
    }
    
    for config_type, define_tag in config_defines.items():
        config_defs = compile_settings.find(f'ns:{define_tag}', ns)
        if config_defs is not None and config_defs.text:
            defs = [d.strip() for d in config_defs.text.split(';') if d.strip() and d != f'%({define_tag})']
            if defs:
                if 'config_defines' not in settings:
                    settings['config_defines'] = {}
                settings['config_defines'][config_type] = defs
    
    # Get force includes
    force_inc = compile_settings.find('ns:ForcedIncludeFiles', ns)
    if force_inc is not None and force_inc.text:
        includes = [i.strip() for i in force_inc.text.split(';') if i.strip() and i != '%(ForcedIncludeFiles)']
        if includes:
            includes = [os.path.relpath(i, '.').replace('\\', '/') for i in includes]
            settings['force_includes'] = includes

def convert_vcxproj(vcxproj_path):
    tree = ET.parse(vcxproj_path)
    root = tree.getroot()
    ns = {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'}
    
    # Initialize CMake content
    cmake_content = []
    cmake_content.append('# Project settings')
    
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
    debug_settings = {}
    release_settings = {}
    profile_settings = {}
    
    for item_def in root.findall('.//ns:ItemDefinitionGroup', ns):
        condition = item_def.get('Condition', '')
        compile_settings = item_def.find('.//ns:ClCompile', ns)
        
        if compile_settings is not None:
            if 'Debug|' in condition:
                _get_configuration_settings(compile_settings, debug_settings, ns)
            elif 'Release|' in condition:
                _get_configuration_settings(compile_settings, release_settings, ns)
            elif 'Profile|' in condition:
                _get_configuration_settings(compile_settings, profile_settings, ns)
    
    # Write configuration-specific settings
    all_include_dirs = set()
    all_defines = set()
    config_specific_defines = []
    
    # Collect all unique settings
    for settings in [debug_settings, release_settings, profile_settings]:
        if settings.get('include_dirs'):
            all_include_dirs.update(settings['include_dirs'])
        if settings.get('defines'):
            all_defines.update(settings['defines'])
    
    # Write include directories
    if all_include_dirs:
        cmake_content.append(f'target_include_directories({project_name} PRIVATE {" ".join(all_include_dirs)})')
    
    # Write common defines
    if all_defines:
        cmake_content.append(f'target_compile_definitions({project_name} PRIVATE {" ".join([f"-D{d}" for d in all_defines])})')
    
    # Handle configuration-specific defines
    for settings, config in [(debug_settings, 'Debug'), (release_settings, 'Release'), (profile_settings, 'Profile')]:
        if settings.get('config_defines', {}).get(config):
            config_defines = settings['config_defines'][config]
            config_specific_defines.append(f'$<$<CONFIG:{config}>:{" ".join([f"-D{d}" for d in config_defines])}>')
    
    # Write configuration-specific defines
    if config_specific_defines:
        cmake_content.append(f'target_compile_definitions({project_name} PRIVATE {" ".join(config_specific_defines)})')
    
    # Write force includes using generator expressions
    force_includes = []
    for settings, config in [(debug_settings, 'Debug'), (release_settings, 'Release'), (profile_settings, 'Profile')]:
        if settings.get('force_includes'):
            force_includes.extend([f'$<$<CONFIG:{config}>:/FI{i}>' for i in settings['force_includes']])
    
    if force_includes:
        cmake_content.append(f'target_compile_options({project_name} PRIVATE {" ".join(force_includes)})')
    
    # Get project references
    for ref in root.findall('.//ns:ProjectReference', ns):
        if 'Include' in ref.attrib:
            dep_name = Path(ref.attrib['Include']).stem
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