import os
import xml.etree.ElementTree as ET
from pathlib import Path

def get_cpp_standard(vcxproj_path, target_config=None):
    """Extract C++ standard version from the vcxproj file"""
    try:
        tree = ET.parse(vcxproj_path)
        root = tree.getroot()
        ns = {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'}
        
        standards = set()
        found_standard = False
        
        # Check ItemDefinitionGroup for LanguageStandard
        for item_def in root.findall('.//ns:ItemDefinitionGroup', ns):
            condition = item_def.get('Condition', '')
            compile_settings = item_def.find('.//ns:ClCompile', ns)
            
            if compile_settings is not None:
                # Skip if target_config specified and this isn't it
                if target_config and "'$(Configuration)|$(Platform)'=='" in condition:
                    config = condition.split("'")[3].split('|')[0]
                    if config != target_config:
                        continue
                
                lang_std = compile_settings.find('ns:LanguageStandard', ns)
                if lang_std is not None and lang_std.text:
                    found_standard = True
                    # Map Visual Studio language standard to CMake standard
                    std_map = {
                        'stdcpp14': 14,
                        'stdcpp17': 17,
                        'stdcpp20': 20,
                        'stdcpplatest': 23,
                        'stdcpp11': 11,
                        'Default': 14  # VS default is typically C++14
                    }
                    
                    std_value = lang_std.text.strip()
                    if std_value in std_map:
                        standards.add(std_map[std_value])
                    elif std_value.startswith('stdcpp'):
                        # Try to extract number from string like "stdcpp17"
                        try:
                            num = int(std_value.replace('stdcpp', ''))
                            standards.add(num)
                        except ValueError:
                            pass
        
        # Also check PropertyGroup for LanguageStandard
        for prop_group in root.findall('.//ns:PropertyGroup', ns):
            condition = prop_group.get('Condition', '')
            
            # Skip if target_config specified and this isn't it
            if target_config and "'$(Configuration)|$(Platform)'=='" in condition:
                config = condition.split("'")[3].split('|')[0]
                if config != target_config:
                    continue
            
            lang_std = prop_group.find('ns:LanguageStandard', ns)
            if lang_std is not None and lang_std.text:
                found_standard = True
                std_map = {
                    'stdcpp14': 14,
                    'stdcpp17': 17,
                    'stdcpp20': 20,
                    'stdcpplatest': 23,
                    'stdcpp11': 11,
                    'Default': 14
                }
                
                std_value = lang_std.text.strip()
                if std_value in std_map:
                    standards.add(std_map[std_value])
        
        # If no LanguageStandard was found, check the PlatformToolset to infer default
        if not found_standard:
            for prop_group in root.findall('.//ns:PropertyGroup', ns):
                toolset = prop_group.find('ns:PlatformToolset', ns)
                if toolset is not None and toolset.text:
                    toolset_value = toolset.text.strip()
                    # Map toolset to default C++ standard
                    # v110 (VS2012) = C++11, v120 (VS2013) = C++11/14, v140 (VS2015) = C++14
                    # v141 (VS2017) = C++14, v142 (VS2019) = C++14, v143 (VS2022) = C++14
                    if toolset_value in ['v110', 'v120']:
                        return 11  # VS2012/2013 defaults to C++11
                    elif toolset_value in ['v140', 'v141', 'v142', 'v143']:
                        return 14  # VS2015/2017/2019/2022 default to C++14
                    break
            # If no toolset found, default to C++14 (most common default)
            return 14
        
        # Return the highest standard found
        return max(standards) if standards else 14
        
    except Exception as e:
        print(f"  Warning: Could not detect C++ standard: {e}")
        return 14  # Default to C++14

def get_windows_version_defines(defines_list, platform_toolset=None):
    """
    Check if Windows version defines are present. If not, return appropriate defaults.
    
    Modern Windows SDKs require _WIN32_WINNT to be defined, otherwise newer APIs
    like KSJACK_SINK_INFORMATION (requires Windows 7+) won't be available.
    
    Returns a list of defines to add (empty if already present or if project
    explicitly sets an older WINVER).
    """
    defines_upper = [d.upper() for d in defines_list] if defines_list else []
    
    has_winnt = any('_WIN32_WINNT' in d for d in defines_upper)
    has_winver = any('WINVER' in d and 'DRIVER' not in d for d in defines_upper)
    has_ntddi = any('NTDDI_VERSION' in d for d in defines_upper)
    
    # Extract existing WINVER value if present
    existing_winver = None
    if has_winver:
        for d in defines_list:
            if 'WINVER' in d.upper() and 'DRIVER' not in d.upper() and '=' in d:
                # Extract the value (e.g., "WINVER=0x502" -> "0x502")
                existing_winver = d.split('=')[1].strip()
                break
    
    additional_defines = []
    
    # If WINVER is already set by the project, respect that choice
    # Don't add _WIN32_WINNT with a potentially conflicting value
    if has_winver:
        # If _WIN32_WINNT is not set but WINVER is, add _WIN32_WINNT to match WINVER
        if not has_winnt and existing_winver:
            additional_defines.append(f'_WIN32_WINNT={existing_winver}')
        # Otherwise, don't add any version defines - project knows what it wants
        return additional_defines
    
    # If none of the version defines are present, add defaults based on toolset
    if not has_winnt:
        # Default to Windows 7 (0x0601) which is the minimum for most modern audio APIs
        # and is reasonable for projects using VS2015+ toolsets
        if platform_toolset:
            if platform_toolset.startswith('v140') or platform_toolset.startswith('v141'):
                # VS2015/VS2017 - target Windows 7
                win_version = '0x0601'
            elif platform_toolset.startswith('v142') or platform_toolset.startswith('v143'):
                # VS2019/VS2022 - target Windows 7 (could also use Windows 10)
                win_version = '0x0601'
            elif '_xp' in platform_toolset.lower():
                # XP toolset - target Windows XP
                win_version = '0x0501'
            else:
                # Default to Windows 7
                win_version = '0x0601'
        else:
            # Default to Windows 7
            win_version = '0x0601'
        
        additional_defines.append(f'_WIN32_WINNT={win_version}')
        
        # Also add WINVER to match if not present
        if not has_winver:
            additional_defines.append(f'WINVER={win_version}')
    
    return additional_defines

def get_platform_toolset(root, ns):
    """Extract platform toolset from the project"""
    for prop_group in root.findall('.//ns:PropertyGroup', ns):
        toolset = prop_group.find('ns:PlatformToolset', ns)
        if toolset is not None and toolset.text:
            return toolset.text.strip()
    return None

def _get_configuration_settings(compile_settings, link_settings, settings, ns, config_name):
    """Extract configuration-specific settings from compile and link settings"""
    
    def convert_include_path(path):
        """
        Convert an include path to the appropriate CMake path variable.
        
        - $(SolutionDir) is replaced with ${CMAKE_SOURCE_DIR}/
        - Paths starting with ../ stay as-is (CMake resolves relative paths correctly)
        - Paths in the current directory (./ or no prefix) stay as-is
        - Already converted paths are cleaned up to prevent doubling
        """
        # First replace Visual Studio variables
        result = path.replace('$(SolutionDir)', '${CMAKE_SOURCE_DIR}/')
        result = result.replace('\\', '/')
        
        # Clean up any double CMAKE_SOURCE_DIR references
        while '${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/' in result:
            result = result.replace('${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/', '${CMAKE_SOURCE_DIR}/')
        
        # Clean up double slashes
        while '//' in result:
            result = result.replace('//', '/')
        
        return result
    
    # Get include directories
    inc_dirs = compile_settings.find('ns:AdditionalIncludeDirectories', ns)
    if inc_dirs is not None and inc_dirs.text:
        dirs = [d.strip() for d in inc_dirs.text.split(';') if d.strip() and d != '%(AdditionalIncludeDirectories)']
        if dirs:
            dirs = [convert_include_path(d) for d in dirs]
            settings['include_dirs'] = dirs
    
    # Get preprocessor definitions
    defines = compile_settings.find('ns:PreprocessorDefinitions', ns)
    if defines is not None and defines.text:
        defs = [d.strip() for d in defines.text.split(';') if d.strip() and d != '%(PreprocessorDefinitions)']
        if defs:
            # Handle backslashes in definitions
            # For path-like definitions (containing drive letters or backslashes), convert to forward slashes
            # This is safer and works on MSVC
            processed_defs = []
            for d in defs:
                if '=' in d and '\\' in d:
                    # This looks like a path definition, convert backslashes to forward slashes
                    name, value = d.split('=', 1)
                    value = value.replace('\\', '/')
                    processed_defs.append(f'{name}={value}')
                else:
                    processed_defs.append(d)
            settings['defines'] = processed_defs
    
    # Get precompiled header settings
    pch_use = compile_settings.find('ns:PrecompiledHeader', ns)
    if pch_use is not None and pch_use.text:
        settings['pch_use'] = pch_use.text  # 'Use', 'Create', 'NotUsing'
    
    pch_file = compile_settings.find('ns:PrecompiledHeaderFile', ns)
    if pch_file is not None and pch_file.text:
        settings['pch_header'] = pch_file.text.replace('\\', '/')
    
    # Get force includes
    force_inc = compile_settings.find('ns:ForcedIncludeFiles', ns)
    if force_inc is not None and force_inc.text:
        includes = [i.strip() for i in force_inc.text.split(';') if i.strip() and i != '%(ForcedIncludeFiles)']
        if includes:
            includes = [i.replace('\\', '/') for i in includes]
            settings['force_includes'] = includes
    
    # Extract compiler flags
    compile_options = []
    
    # AdditionalOptions - raw compiler flags like /MP, /d2Zi+, etc.
    additional_opts = compile_settings.find('ns:AdditionalOptions', ns)
    if additional_opts is not None and additional_opts.text:
        opts = [o.strip() for o in additional_opts.text.split() if o.strip() and o != '%(AdditionalOptions)']
        compile_options.extend(opts)
    
    # MultiProcessorCompilation -> /MP
    mp_compile = compile_settings.find('ns:MultiProcessorCompilation', ns)
    if mp_compile is not None and mp_compile.text and mp_compile.text.lower() == 'true':
        if '/MP' not in compile_options:
            compile_options.append('/MP')
    
    # Optimization
    optimization = compile_settings.find('ns:Optimization', ns)
    if optimization is not None and optimization.text:
        opt_map = {
            'Disabled': '/Od',
            'MinSpace': '/O1',
            'MaxSpeed': '/O2',
            'Full': '/Ox'
        }
        if optimization.text in opt_map:
            compile_options.append(opt_map[optimization.text])
    
    # InlineFunctionExpansion
    inline_func = compile_settings.find('ns:InlineFunctionExpansion', ns)
    if inline_func is not None and inline_func.text:
        inline_map = {
            'Disabled': '/Ob0',
            'OnlyExplicitInline': '/Ob1',
            'AnySuitable': '/Ob2'
        }
        if inline_func.text in inline_map:
            compile_options.append(inline_map[inline_func.text])
    
    # IntrinsicFunctions
    intrinsic = compile_settings.find('ns:IntrinsicFunctions', ns)
    if intrinsic is not None and intrinsic.text and intrinsic.text.lower() == 'true':
        compile_options.append('/Oi')
    
    # FavorSizeOrSpeed
    favor = compile_settings.find('ns:FavorSizeOrSpeed', ns)
    if favor is not None and favor.text:
        favor_map = {
            'Speed': '/Ot',
            'Size': '/Os'
        }
        if favor.text in favor_map:
            compile_options.append(favor_map[favor.text])
    
    # StringPooling
    string_pool = compile_settings.find('ns:StringPooling', ns)
    if string_pool is not None and string_pool.text and string_pool.text.lower() == 'true':
        compile_options.append('/GF')
    
    # ExceptionHandling
    exception = compile_settings.find('ns:ExceptionHandling', ns)
    if exception is not None and exception.text:
        exc_map = {
            'false': '',  # No flag needed
            'Sync': '/EHsc',
            'Async': '/EHa',
            'SyncCThrow': '/EHs'
        }
        if exception.text in exc_map and exc_map[exception.text]:
            compile_options.append(exc_map[exception.text])
    
    # RuntimeLibrary
    runtime_lib = compile_settings.find('ns:RuntimeLibrary', ns)
    if runtime_lib is not None and runtime_lib.text:
        rt_map = {
            'MultiThreaded': '/MT',
            'MultiThreadedDebug': '/MTd',
            'MultiThreadedDLL': '/MD',
            'MultiThreadedDebugDLL': '/MDd'
        }
        if runtime_lib.text in rt_map:
            settings['runtime_library_flag'] = rt_map[runtime_lib.text]
    
    # BufferSecurityCheck
    buffer_check = compile_settings.find('ns:BufferSecurityCheck', ns)
    if buffer_check is not None and buffer_check.text:
        if buffer_check.text.lower() == 'false':
            compile_options.append('/GS-')
        elif buffer_check.text.lower() == 'true':
            compile_options.append('/GS')
    
    # FunctionLevelLinking
    func_link = compile_settings.find('ns:FunctionLevelLinking', ns)
    if func_link is not None and func_link.text and func_link.text.lower() == 'true':
        compile_options.append('/Gy')
    
    # EnableEnhancedInstructionSet
    simd = compile_settings.find('ns:EnableEnhancedInstructionSet', ns)
    if simd is not None and simd.text:
        simd_map = {
            'StreamingSIMDExtensions': '/arch:SSE',
            'StreamingSIMDExtensions2': '/arch:SSE2',
            'AdvancedVectorExtensions': '/arch:AVX',
            'AdvancedVectorExtensions2': '/arch:AVX2',
            'AdvancedVectorExtensions512': '/arch:AVX512'
        }
        if simd.text in simd_map:
            compile_options.append(simd_map[simd.text])
    
    # FloatingPointModel
    fp_model = compile_settings.find('ns:FloatingPointModel', ns)
    if fp_model is not None and fp_model.text:
        fp_map = {
            'Precise': '/fp:precise',
            'Strict': '/fp:strict',
            'Fast': '/fp:fast'
        }
        if fp_model.text in fp_map:
            compile_options.append(fp_map[fp_model.text])
    
    # RuntimeTypeInfo (RTTI)
    rtti = compile_settings.find('ns:RuntimeTypeInfo', ns)
    if rtti is not None and rtti.text:
        if rtti.text.lower() == 'true':
            compile_options.append('/GR')
        elif rtti.text.lower() == 'false':
            compile_options.append('/GR-')
    
    # WarningLevel
    warn_level = compile_settings.find('ns:WarningLevel', ns)
    if warn_level is not None and warn_level.text:
        warn_map = {
            'TurnOffAllWarnings': '/W0',
            'Level1': '/W1',
            'Level2': '/W2',
            'Level3': '/W3',
            'Level4': '/W4',
            'EnableAllWarnings': '/Wall'
        }
        if warn_level.text in warn_map:
            compile_options.append(warn_map[warn_level.text])
    
    # TreatWarningAsError
    warn_error = compile_settings.find('ns:TreatWarningAsError', ns)
    if warn_error is not None and warn_error.text and warn_error.text.lower() == 'true':
        compile_options.append('/WX')
    
    # DisableSpecificWarnings
    disable_warn = compile_settings.find('ns:DisableSpecificWarnings', ns)
    if disable_warn is not None and disable_warn.text:
        warnings = [w.strip() for w in disable_warn.text.split(';') if w.strip() and w != '%(DisableSpecificWarnings)']
        for w in warnings:
            compile_options.append(f'/wd{w}')
    
    # DebugInformationFormat
    debug_info = compile_settings.find('ns:DebugInformationFormat', ns)
    if debug_info is not None and debug_info.text:
        debug_map = {
            'None': '',
            'OldStyle': '/Z7',
            'ProgramDatabase': '/Zi',
            'EditAndContinue': '/ZI'
        }
        if debug_info.text in debug_map and debug_map[debug_info.text]:
            compile_options.append(debug_map[debug_info.text])
    
    # MinimalRebuild (deprecated but still used)
    minimal_rebuild = compile_settings.find('ns:MinimalRebuild', ns)
    if minimal_rebuild is not None and minimal_rebuild.text and minimal_rebuild.text.lower() == 'true':
        compile_options.append('/Gm')
    
    # BasicRuntimeChecks - these are incompatible with optimization (/O1, /O2, /Ox)
    # Only add RTC flags if explicitly set (not 'Default') 
    # Visual Studio automatically disables these for Release builds
    runtime_checks = compile_settings.find('ns:BasicRuntimeChecks', ns)
    if runtime_checks is not None and runtime_checks.text:
        rtc_value = runtime_checks.text.strip()
        # Skip 'Default' - it means use configuration default (no RTC for Release, RTC1 for Debug)
        # We'll let the build configuration handle this automatically
        if rtc_value != 'Default':
            rtc_map = {
                'StackFrameRuntimeCheck': '/RTCs',
                'UninitializedLocalUsageCheck': '/RTCu',
                'EnableFastChecks': '/RTC1'
            }
            if rtc_value in rtc_map:
                compile_options.append(rtc_map[rtc_value])
    
    # SmallerTypeCheck
    smaller_type = compile_settings.find('ns:SmallerTypeCheck', ns)
    if smaller_type is not None and smaller_type.text and smaller_type.text.lower() == 'true':
        compile_options.append('/RTCc')
    
    # OmitFramePointers
    omit_fp = compile_settings.find('ns:OmitFramePointers', ns)
    if omit_fp is not None and omit_fp.text:
        if omit_fp.text.lower() == 'true':
            compile_options.append('/Oy')
        elif omit_fp.text.lower() == 'false':
            compile_options.append('/Oy-')
    
    # WholeProgramOptimization
    wpo = compile_settings.find('ns:WholeProgramOptimization', ns)
    if wpo is not None and wpo.text and wpo.text.lower() == 'true':
        compile_options.append('/GL')
    
    # CallingConvention
    calling_conv = compile_settings.find('ns:CallingConvention', ns)
    if calling_conv is not None and calling_conv.text:
        cc_map = {
            'Cdecl': '/Gd',
            'FastCall': '/Gr',
            'StdCall': '/Gz',
            'VectorCall': '/Gv'
        }
        if calling_conv.text in cc_map:
            compile_options.append(cc_map[calling_conv.text])
    
    # StructMemberAlignment
    struct_align = compile_settings.find('ns:StructMemberAlignment', ns)
    if struct_align is not None and struct_align.text:
        align_map = {
            '1Byte': '/Zp1',
            '2Bytes': '/Zp2',
            '4Bytes': '/Zp4',
            '8Bytes': '/Zp8',
            '16Bytes': '/Zp16'
        }
        if struct_align.text in align_map:
            compile_options.append(align_map[struct_align.text])
    
    # EnableFiberSafeOptimizations
    fiber_safe = compile_settings.find('ns:EnableFiberSafeOptimizations', ns)
    if fiber_safe is not None and fiber_safe.text and fiber_safe.text.lower() == 'true':
        compile_options.append('/GT')
    
    # OpenMPSupport
    openmp = compile_settings.find('ns:OpenMPSupport', ns)
    if openmp is not None and openmp.text and openmp.text.lower() == 'true':
        compile_options.append('/openmp')
    
    # LanguageStandard (C++)
    lang_std = compile_settings.find('ns:LanguageStandard', ns)
    if lang_std is not None and lang_std.text:
        std_map = {
            'stdcpp14': '/std:c++14',
            'stdcpp17': '/std:c++17',
            'stdcpp20': '/std:c++20',
            'stdcpplatest': '/std:c++latest'
        }
        if lang_std.text in std_map:
            compile_options.append(std_map[lang_std.text])
    
    # LanguageStandard_C (C)
    lang_std_c = compile_settings.find('ns:LanguageStandard_C', ns)
    if lang_std_c is not None and lang_std_c.text:
        c_std_map = {
            'stdc11': '/std:c11',
            'stdc17': '/std:c17'
        }
        if lang_std_c.text in c_std_map:
            compile_options.append(c_std_map[lang_std_c.text])
    
    # ConformanceMode
    conformance = compile_settings.find('ns:ConformanceMode', ns)
    if conformance is not None and conformance.text and conformance.text.lower() == 'true':
        compile_options.append('/permissive-')
    
    # SDLCheck
    sdl_check = compile_settings.find('ns:SDLCheck', ns)
    if sdl_check is not None and sdl_check.text and sdl_check.text.lower() == 'true':
        compile_options.append('/sdl')
    
    # TreatSpecificWarningsAsErrors
    warn_as_err = compile_settings.find('ns:TreatSpecificWarningsAsErrors', ns)
    if warn_as_err is not None and warn_as_err.text:
        warnings = [w.strip() for w in warn_as_err.text.split(';') if w.strip() and w != '%(TreatSpecificWarningsAsErrors)']
        for w in warnings:
            compile_options.append(f'/we{w}')
    
    if compile_options:
        settings['compile_options'] = compile_options
    
    # Extract linker flags
    link_options = []
    
    if link_settings is not None:
        # AdditionalOptions for linker
        link_additional = link_settings.find('ns:AdditionalOptions', ns)
        if link_additional is not None and link_additional.text:
            opts = [o.strip() for o in link_additional.text.split() if o.strip() and o != '%(AdditionalOptions)']
            link_options.extend(opts)
        
        # GenerateDebugInformation
        gen_debug = link_settings.find('ns:GenerateDebugInformation', ns)
        if gen_debug is not None and gen_debug.text:
            if gen_debug.text.lower() == 'true':
                link_options.append('/DEBUG')
            elif gen_debug.text == 'DebugFastLink':
                link_options.append('/DEBUG:FASTLINK')
            elif gen_debug.text == 'DebugFull':
                link_options.append('/DEBUG:FULL')
        
        # OptimizeReferences
        opt_ref = link_settings.find('ns:OptimizeReferences', ns)
        if opt_ref is not None and opt_ref.text and opt_ref.text.lower() == 'true':
            link_options.append('/OPT:REF')
        
        # EnableCOMDATFolding
        comdat = link_settings.find('ns:EnableCOMDATFolding', ns)
        if comdat is not None and comdat.text and comdat.text.lower() == 'true':
            link_options.append('/OPT:ICF')
        
        # LinkTimeCodeGeneration (LTCG)
        ltcg = link_settings.find('ns:LinkTimeCodeGeneration', ns)
        if ltcg is not None and ltcg.text:
            ltcg_map = {
                'UseLinkTimeCodeGeneration': '/LTCG',
                'PGInstrument': '/LTCG:PGInstrument',
                'PGOptimization': '/LTCG:PGOptimize',
                'PGUpdate': '/LTCG:PGUpdate'
            }
            if ltcg.text in ltcg_map:
                link_options.append(ltcg_map[ltcg.text])
        
        # SubSystem
        subsystem = link_settings.find('ns:SubSystem', ns)
        if subsystem is not None and subsystem.text:
            sub_map = {
                'Console': '/SUBSYSTEM:CONSOLE',
                'Windows': '/SUBSYSTEM:WINDOWS',
                'Native': '/SUBSYSTEM:NATIVE',
                'EFI Application': '/SUBSYSTEM:EFI_APPLICATION',
                'EFI Boot Service Driver': '/SUBSYSTEM:EFI_BOOT_SERVICE_DRIVER',
                'EFI ROM': '/SUBSYSTEM:EFI_ROM',
                'EFI Runtime': '/SUBSYSTEM:EFI_RUNTIME_DRIVER',
                'POSIX': '/SUBSYSTEM:POSIX'
            }
            if subsystem.text in sub_map:
                link_options.append(sub_map[subsystem.text])
        
        # IgnoreSpecificDefaultLibraries
        ignore_libs = link_settings.find('ns:IgnoreSpecificDefaultLibraries', ns)
        if ignore_libs is not None and ignore_libs.text:
            libs = [l.strip() for l in ignore_libs.text.split(';') if l.strip() and l != '%(IgnoreSpecificDefaultLibraries)']
            for lib in libs:
                link_options.append(f'/NODEFAULTLIB:{lib}')
        
        # LargeAddressAware
        large_addr = link_settings.find('ns:LargeAddressAware', ns)
        if large_addr is not None and large_addr.text and large_addr.text.lower() == 'true':
            link_options.append('/LARGEADDRESSAWARE')
        
        # RandomizedBaseAddress (ASLR)
        aslr = link_settings.find('ns:RandomizedBaseAddress', ns)
        if aslr is not None and aslr.text:
            if aslr.text.lower() == 'true':
                link_options.append('/DYNAMICBASE')
            elif aslr.text.lower() == 'false':
                link_options.append('/DYNAMICBASE:NO')
        
        # DataExecutionPrevention (DEP/NX)
        dep = link_settings.find('ns:DataExecutionPrevention', ns)
        if dep is not None and dep.text:
            if dep.text.lower() == 'true':
                link_options.append('/NXCOMPAT')
            elif dep.text.lower() == 'false':
                link_options.append('/NXCOMPAT:NO')
        
        # ImageHasSafeExceptionHandlers (SafeSEH)
        safe_seh = link_settings.find('ns:ImageHasSafeExceptionHandlers', ns)
        if safe_seh is not None and safe_seh.text:
            if safe_seh.text.lower() == 'true':
                link_options.append('/SAFESEH')
            elif safe_seh.text.lower() == 'false':
                link_options.append('/SAFESEH:NO')
        
        # TargetMachine
        target_machine = link_settings.find('ns:TargetMachine', ns)
        if target_machine is not None and target_machine.text:
            machine_map = {
                'MachineX86': '/MACHINE:X86',
                'MachineX64': '/MACHINE:X64',
                'MachineARM': '/MACHINE:ARM',
                'MachineARM64': '/MACHINE:ARM64'
            }
            if target_machine.text in machine_map:
                link_options.append(machine_map[target_machine.text])
        
        # AdditionalDependencies (libraries)
        additional_deps = link_settings.find('ns:AdditionalDependencies', ns)
        if additional_deps is not None and additional_deps.text:
            libs = [lib.strip() for lib in additional_deps.text.split(';') 
                   if lib.strip() and lib.strip() not in ['%(AdditionalDependencies)', '']]
            if libs:
                # Escape backslashes in library paths for CMake
                libs = [lib.replace('\\', '\\\\') for lib in libs]
                settings['libraries'] = libs
        
        # AdditionalLibraryDirectories
        lib_dirs = link_settings.find('ns:AdditionalLibraryDirectories', ns)
        if lib_dirs is not None and lib_dirs.text:
            dirs = [d.strip() for d in lib_dirs.text.split(';') 
                   if d.strip() and d != '%(AdditionalLibraryDirectories)']
            if dirs:
                processed_dirs = []
                for d in dirs:
                    # Replace VS variables first
                    d = d.replace('$(SolutionDir)', '${CMAKE_SOURCE_DIR}/').replace('\\', '/')
                    # Clean up any double CMAKE_SOURCE_DIR references  
                    while '${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/' in d:
                        d = d.replace('${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/', '${CMAKE_SOURCE_DIR}/')
                    # Clean up double slashes
                    while '//' in d:
                        d = d.replace('//', '/')
                    processed_dirs.append(d)
                settings['library_dirs'] = processed_dirs
        
        # OutputFile - the output DLL/EXE name
        output_file = link_settings.find('ns:OutputFile', ns)
        if output_file is not None and output_file.text:
            output_path = output_file.text.strip()
            # Normalize path separators
            output_path = output_path.replace('\\', '/')
            settings['output_file'] = output_path
        
        # ImportLibrary - where the import library (.lib) is placed for DLLs
        import_lib = link_settings.find('ns:ImportLibrary', ns)
        if import_lib is not None and import_lib.text:
            import_path = import_lib.text.strip()
            # Normalize path separators
            import_path = import_path.replace('\\', '/')
            settings['import_library'] = import_path
        
        # ProgramDatabaseFile - where the PDB goes
        pdb_file = link_settings.find('ns:ProgramDatabaseFile', ns)
        if pdb_file is not None and pdb_file.text:
            pdb_path = pdb_file.text.strip()
            pdb_path = pdb_path.replace('\\', '/')
            settings['pdb_file'] = pdb_path
    
    if link_options:
        settings['link_options'] = link_options

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

def is_file_excluded(element, ns, target_config=None):
    """Check if a file is excluded from build configuration(s)"""
    # Check for direct ExcludedFromBuild without condition (applies to all configs)
    excluded = element.find('ns:ExcludedFromBuild', ns)
    if excluded is not None and excluded.text and excluded.text.strip().lower() == 'true':
        return True
    
    # If target_config specified, only check that specific configuration
    if target_config:
        # Check for condition-based exclusions for the target config
        for child in element:
            if child.tag.endswith('ExcludedFromBuild'):
                condition = child.get('Condition', '')
                if condition:
                    # Extract config from condition like "'$(Configuration)|$(Platform)'=='Debug|Win32'"
                    if "'$(Configuration)|$(Platform)'=='" in condition:
                        config_platform = condition.split("'")[3]
                        config = config_platform.split('|')[0]
                        if config == target_config and child.text and child.text.strip().lower() == 'true':
                            return True
    else:
        # No target_config: if excluded from ANY configuration, mark as excluded
        for child in element:
            if child.tag.endswith('ExcludedFromBuild'):
                if child.text and child.text.strip().lower() == 'true':
                    return True
    
    return False

def get_file_specific_includes(element, ns, target_config=None):
    """Extract file-specific include directories"""
    include_dirs = set()
    
    # Look for AdditionalIncludeDirectories in the file element
    if target_config:
        # Check for condition-specific includes
        for child in element:
            if child.tag.endswith('AdditionalIncludeDirectories'):
                condition = child.get('Condition', '')
                if condition:
                    if "'$(Configuration)|$(Platform)'=='" in condition:
                        config_platform = condition.split("'")[3]
                        config = config_platform.split('|')[0]
                        if config == target_config and child.text:
                            dirs = [d.strip() for d in child.text.split(';') 
                                   if d.strip() and d != '%(AdditionalIncludeDirectories)']
                            include_dirs.update(dirs)
                elif child.text:
                    # No condition means applies to all configs
                    dirs = [d.strip() for d in child.text.split(';') 
                           if d.strip() and d != '%(AdditionalIncludeDirectories)']
                    include_dirs.update(dirs)
    else:
        # Get all includes from all configurations
        for child in element:
            if child.tag.endswith('AdditionalIncludeDirectories') and child.text:
                dirs = [d.strip() for d in child.text.split(';') 
                       if d.strip() and d != '%(AdditionalIncludeDirectories)']
                include_dirs.update(dirs)
    
    # Also check direct AdditionalIncludeDirectories element without iteration
    inc_dirs = element.find('ns:AdditionalIncludeDirectories', ns)
    if inc_dirs is not None and inc_dirs.text:
        dirs = [d.strip() for d in inc_dirs.text.split(';') 
               if d.strip() and d != '%(AdditionalIncludeDirectories)']
        include_dirs.update(dirs)
    
    if include_dirs:
        # Normalize paths
        result = []
        for d in include_dirs:
            path = d.replace('$(SolutionDir)', '${CMAKE_SOURCE_DIR}/').replace('\\', '/')
            # Clean up any double CMAKE_SOURCE_DIR references
            while '${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/' in path:
                path = path.replace('${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/', '${CMAKE_SOURCE_DIR}/')
            # Clean up double slashes
            while '//' in path:
                path = path.replace('//', '/')
            result.append(path)
        return result
    return []

def get_file_specific_options(element, ns, target_config=None):
    """Extract file-specific compiler options"""
    options = {
        'compile_as': None,
        'runtime_library': None,
        'warning_level': None,
        'preprocessor_defs': [],
        'pch_mode': None,  # 'Use', 'Create', 'NotUsing'
        'pch_header': None
    }
    
    # Helper to extract value based on config
    def get_value(tag_name):
        if target_config:
            # Check condition-specific first
            for child in element:
                if child.tag.endswith(tag_name):
                    condition = child.get('Condition', '')
                    if condition:
                        if "'$(Configuration)|$(Platform)'=='" in condition:
                            config_platform = condition.split("'")[3]
                            config = config_platform.split('|')[0]
                            if config == target_config and child.text:
                                return child.text.strip()
                    elif child.text:
                        return child.text.strip()
        
        # Check direct element
        elem = element.find(f'ns:{tag_name}', ns)
        if elem is not None and elem.text:
            return elem.text.strip()
        return None
    
    # Get CompileAs option
    compile_as = get_value('CompileAs')
    if compile_as:
        options['compile_as'] = compile_as
    
    # Get RuntimeLibrary option (for MFC)
    runtime_lib = get_value('RuntimeLibrary')
    if runtime_lib:
        options['runtime_library'] = runtime_lib
    
    # Get WarningLevel
    warning_level = get_value('WarningLevel')
    if warning_level:
        options['warning_level'] = warning_level
    
    # Get PreprocessorDefinitions
    preprocessor = get_value('PreprocessorDefinitions')
    if preprocessor:
        defs = [d.strip() for d in preprocessor.split(';') 
               if d.strip() and d != '%(PreprocessorDefinitions)']
        # Handle backslashes in definitions - convert path-like values to forward slashes
        processed_defs = []
        for d in defs:
            if '=' in d and '\\' in d:
                # This looks like a path definition, convert backslashes to forward slashes
                name, value = d.split('=', 1)
                value = value.replace('\\', '/')
                processed_defs.append(f'{name}={value}')
            else:
                processed_defs.append(d)
        options['preprocessor_defs'] = processed_defs
    
    # Get PrecompiledHeader mode (Create, Use, NotUsing)
    pch_mode = get_value('PrecompiledHeader')
    if pch_mode:
        options['pch_mode'] = pch_mode
    
    # Get PrecompiledHeaderFile
    pch_header = get_value('PrecompiledHeaderFile')
    if pch_header:
        options['pch_header'] = pch_header.replace('\\', '/')
    
    return options

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

def get_mfc_settings(root, ns, config_name='Debug'):
    """Get MFC usage settings and runtime library configuration"""
    mfc_settings = {
        'use_mfc': None,  # UseOfMfc value
        'use_afx_dll': False,  # Whether _AFXDLL should be defined
        'runtime_library': None  # RuntimeLibrary setting from vcxproj
    }
    
    # First, get runtime library setting from the vcxproj
    for item_def in root.findall('.//ns:ItemDefinitionGroup', ns):
        condition = item_def.get('Condition', '')
        if f"'{config_name}|" in condition or not condition:
            compile_settings = item_def.find('.//ns:ClCompile', ns)
            if compile_settings is not None:
                rt_lib = compile_settings.find('ns:RuntimeLibrary', ns)
                if rt_lib is not None and rt_lib.text:
                    mfc_settings['runtime_library'] = rt_lib.text.strip()
                    break
    
    # Look for UseOfMfc in PropertyGroup elements
    for prop_group in root.findall('.//ns:PropertyGroup', ns):
        condition = prop_group.get('Condition', '')
        label = prop_group.get('Label', '')
        
        # Check config-specific, configuration label groups, or groups with no condition
        if f"'{config_name}|" in condition or label == 'Configuration' or not condition:
            use_mfc = prop_group.find('ns:UseOfMfc', ns)
            if use_mfc is not None and use_mfc.text:
                mfc_value = use_mfc.text.strip()
                mfc_settings['use_mfc'] = mfc_value
                # Dynamic = shared DLL, Static = static lib
                if mfc_value == 'Dynamic' or mfc_value == 'true':
                    mfc_settings['use_afx_dll'] = True
                    return mfc_settings  # Found it, return early
    
    # If not explicitly set, try to infer from other indicators
    if mfc_settings['use_mfc'] is None:
        has_mfc_indicator = False
        has_afxdll_define = False
        runtime_library = mfc_settings['runtime_library']
        
        # Check for MFC-related files
        for item in root.findall('.//ns:ClCompile', ns):
            if 'Include' in item.attrib:
                file_path = item.attrib['Include']
                if 'afxmem_override.cpp' in file_path.lower() or 'afx' in file_path.lower():
                    has_mfc_indicator = True
                    break
        
        # Check for MFC-related preprocessor definitions
        for item_def in root.findall('.//ns:ItemDefinitionGroup', ns):
            condition = item_def.get('Condition', '')
            if f"'{config_name}|" in condition or not condition:
                compile_settings = item_def.find('.//ns:ClCompile', ns)
                if compile_settings is not None:
                    defines = compile_settings.find('ns:PreprocessorDefinitions', ns)
                    if defines is not None and defines.text:
                        if 'NO_WARN_MBCS_MFC_DEPRECATION' in defines.text:
                            has_mfc_indicator = True
                        if '_AFXDLL' in defines.text:
                            has_afxdll_define = True
        
        # Infer MFC usage
        if has_mfc_indicator:
            if has_afxdll_define:
                mfc_settings['use_mfc'] = 'Dynamic'
                mfc_settings['use_afx_dll'] = True
            else:
                # Check runtime library - if static CRT, must use static MFC
                if runtime_library in ['MultiThreaded', 'MultiThreadedDebug']:
                    mfc_settings['use_mfc'] = 'Static'
                    mfc_settings['use_afx_dll'] = False
                else:
                    # If no _AFXDLL but runtime is dynamic, default to static MFC
                    # (safer assumption)
                    mfc_settings['use_mfc'] = 'Static'
                    mfc_settings['use_afx_dll'] = False
    
    return mfc_settings

def get_project_name(root, ns, fallback_name):
    """Get the project name from PropertyGroup, with fallback"""
    # Look for ProjectName in PropertyGroup
    for prop_group in root.findall('.//ns:PropertyGroup', ns):
        project_name = prop_group.find('ns:ProjectName', ns)
        if project_name is not None and project_name.text:
            return project_name.text
    
    # Fallback to the provided name
    return fallback_name


def get_output_settings(root, ns, target_config=None):
    """
    Extract output-related settings from PropertyGroup elements.
    
    Returns a dict with settings per configuration:
    {
        'Debug': {
            'out_dir': '...',
            'int_dir': '...',
            'target_name': '...',
        },
        ...
    }
    """
    output_settings = {}
    
    # First, get target name (usually not config-specific)
    global_target_name = None
    for prop_group in root.findall('.//ns:PropertyGroup', ns):
        target_name = prop_group.find('ns:TargetName', ns)
        if target_name is not None and target_name.text:
            condition = prop_group.get('Condition', '')
            if not condition:
                global_target_name = target_name.text.strip()
            elif target_config and f"'{target_config}|" in condition:
                global_target_name = target_name.text.strip()
    
    # Get config-specific settings
    for prop_group in root.findall('.//ns:PropertyGroup', ns):
        condition = prop_group.get('Condition', '')
        
        # Extract config name from condition
        config_name = None
        if "'$(Configuration)|$(Platform)'=='" in condition:
            config_platform = condition.split("'")[3]
            config_name = config_platform.split('|')[0]
        
        # Skip if target_config specified and this isn't it
        if target_config and config_name and config_name != target_config:
            continue
        
        # Initialize config settings if needed
        if config_name and config_name not in output_settings:
            output_settings[config_name] = {
                'target_name': global_target_name
            }
        
        # Extract OutDir
        out_dir = prop_group.find('ns:OutDir', ns)
        if out_dir is not None and out_dir.text and config_name:
            output_settings[config_name]['out_dir'] = out_dir.text.strip().replace('\\', '/')
        
        # Extract IntDir
        int_dir = prop_group.find('ns:IntDir', ns)
        if int_dir is not None and int_dir.text and config_name:
            output_settings[config_name]['int_dir'] = int_dir.text.strip().replace('\\', '/')
        
        # Config-specific TargetName (overrides global)
        target_name = prop_group.find('ns:TargetName', ns)
        if target_name is not None and target_name.text and config_name:
            output_settings[config_name]['target_name'] = target_name.text.strip()
        
        # TargetExt - output extension
        target_ext = prop_group.find('ns:TargetExt', ns)
        if target_ext is not None and target_ext.text and config_name:
            output_settings[config_name]['target_ext'] = target_ext.text.strip()
    
    return output_settings, global_target_name

def convert_vcxproj(vcxproj_path, target_config=None, solution_cpp_standard=None, solution_projects=None):
    """
    Convert a vcxproj file to CMake.
    
    Args:
        vcxproj_path: Path to the .vcxproj file
        target_config: Optional specific configuration to convert (e.g., 'Debug', 'Release')
        solution_cpp_standard: C++ standard from solution level
        solution_projects: Dict mapping lowercase project names to their proper-case CMake target names.
                          Used to determine if a library dependency should be linked as a CMake target 
                          vs external library path, and to get the correct casing for target names.
    """
    # Default to empty dict if not provided
    if solution_projects is None:
        solution_projects = {}
    
    # solution_projects is now a dict of lowercase -> proper case
    # For backward compatibility, if it's a set, convert it to a dict
    if isinstance(solution_projects, set):
        solution_projects_lower = {name.lower(): name for name in solution_projects}
    else:
        # It's already a dict in the correct format
        solution_projects_lower = solution_projects
    
    tree = ET.parse(vcxproj_path)
    root = tree.getroot()
    ns = {'ns': 'http://schemas.microsoft.com/developer/msbuild/2003'}
    
    # Initialize CMake content
    cmake_content = []
    
    # Get project name (prefer ProjectName from PropertyGroup, fallback to filename)
    fallback_name = Path(vcxproj_path).stem
    project_name = get_project_name(root, ns, fallback_name)
    
    # Sanitize project name for CMake (replace invalid characters)
    project_name = project_name.replace('-', '_').replace(' ', '_').replace('(', '_').replace(')', '_')
    
    print(f"  Using project name: {project_name}")
    
    # Get C++ standard for this project if not provided
    if solution_cpp_standard is None:
        project_cpp_standard = get_cpp_standard(vcxproj_path, target_config)
    else:
        project_cpp_standard = solution_cpp_standard
    
    # Get configurations
    configurations = get_configurations(root, ns)
    
    # If target_config specified, validate it exists
    if target_config:
        if target_config not in configurations:
            print(f"  WARNING: Specified configuration '{target_config}' not found in project.")
            print(f"  Available configurations: {', '.join(configurations)}")
            print(f"  Using '{target_config}' anyway...")
        else:
            print(f"  Converting settings for configuration: {target_config}")
    
    # Get source files (including those marked as ExcludedFromBuild)
    sources = []
    headers = []
    excluded_sources = []
    excluded_headers = []
    file_specific_includes = {}
    file_specific_options = {}
    
    for item_group in root.findall('.//ns:ClCompile', ns):
        if 'Include' in item_group.attrib:
            file_path = item_group.attrib['Include'].replace('\\', '/')
            sources.append(file_path)
            
            if is_file_excluded(item_group, ns, target_config):
                excluded_sources.append(file_path)
                print(f"  Excluding source from build: {file_path}")
            
            # Check for file-specific include directories
            file_includes = get_file_specific_includes(item_group, ns, target_config)
            if file_includes:
                file_specific_includes[file_path] = file_includes
                print(f"  File-specific includes for {file_path}: {', '.join(file_includes)}")
            
            # Check for file-specific compiler options
            file_options = get_file_specific_options(item_group, ns, target_config)
            if any([file_options['compile_as'], file_options['runtime_library'], 
                   file_options['warning_level'], file_options['preprocessor_defs'],
                   file_options['pch_mode']]):
                file_specific_options[file_path] = file_options
                if file_options['compile_as']:
                    print(f"  File-specific CompileAs for {file_path}: {file_options['compile_as']}")
                if file_options['runtime_library']:
                    print(f"  File-specific RuntimeLibrary for {file_path}: {file_options['runtime_library']}")
                if file_options['warning_level']:
                    print(f"  File-specific WarningLevel for {file_path}: {file_options['warning_level']}")
                if file_options['preprocessor_defs']:
                    print(f"  File-specific defines for {file_path}: {', '.join(file_options['preprocessor_defs'])}")
                if file_options['pch_mode']:
                    print(f"  File-specific PCH mode for {file_path}: {file_options['pch_mode']}")
    
    for item_group in root.findall('.//ns:ClInclude', ns):
        if 'Include' in item_group.attrib:
            file_path = item_group.attrib['Include'].replace('\\', '/')
            headers.append(file_path)
            
            if is_file_excluded(item_group, ns, target_config):
                excluded_headers.append(file_path)
                print(f"  Excluding header from build: {file_path}")
    
    # Report exclusions
    if excluded_sources or excluded_headers:
        print(f"  Total excluded: {len(excluded_sources)} source(s), {len(excluded_headers)} header(s)")
    
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
    project_type = get_project_type(root, ns, target_config if target_config else 'Debug')
    is_lib = 'StaticLibrary' in project_type or 'DynamicLibrary' in project_type
    
    # Get MFC settings
    mfc_settings = get_mfc_settings(root, ns, target_config if target_config else 'Debug')
    if mfc_settings['use_mfc']:
        print(f"  MFC Usage: {mfc_settings['use_mfc']}")
        if mfc_settings['runtime_library']:
            print(f"  Runtime Library: {mfc_settings['runtime_library']}")
        if mfc_settings['use_afx_dll']:
            print(f"  Adding _AFXDLL define for dynamic MFC")
    
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
    
    # Add MFC settings if needed
    if mfc_settings['use_mfc']:
        cmake_content.append('')
        cmake_content.append(f'# MFC configuration - {mfc_settings["use_mfc"]} MFC')
        cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
        if mfc_settings['use_mfc'] == 'Static':
            cmake_content.append('    VS_MFC_FLAG 1  # 1 = Use MFC in a Static Library')
        else:
            cmake_content.append('    VS_MFC_FLAG 2  # 2 = Use MFC in a Shared DLL')
        cmake_content.append(')')
        
        # CRITICAL: Set the runtime library to match MFC configuration
        # Static MFC requires static CRT (/MT or /MTd)
        # Dynamic MFC requires dynamic CRT (/MD or /MDd) and _AFXDLL
        cmake_content.append('')
        cmake_content.append('# Runtime library must match MFC configuration')
        
        if mfc_settings['use_mfc'] == 'Static':
            # Static MFC requires /MT (Release) or /MTd (Debug)
            cmake_content.append(f'set_property(TARGET {project_name} PROPERTY')
            cmake_content.append('    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")')
        else:
            # Dynamic MFC requires /MD (Release) or /MDd (Debug)
            cmake_content.append(f'set_property(TARGET {project_name} PROPERTY')
            cmake_content.append('    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")')
            # Also need to ensure _AFXDLL is defined for dynamic MFC
            cmake_content.append('')
            cmake_content.append('# _AFXDLL is required for dynamic MFC')
            cmake_content.append(f'target_compile_definitions({project_name} PRIVATE _AFXDLL)')
    
    # Set project-specific C++ standard if different from solution standard
    if solution_cpp_standard and project_cpp_standard != solution_cpp_standard:
        cmake_content.append('')
        cmake_content.append(f'# Override C++ standard for this project')
        cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
        cmake_content.append(f'    CXX_STANDARD {project_cpp_standard}')
        cmake_content.append(f'    CXX_STANDARD_REQUIRED ON')
        cmake_content.append(')')
    
    # Get output settings (OutDir, IntDir, TargetName from PropertyGroup)
    output_settings, global_target_name = get_output_settings(root, ns, target_config)
    
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
            
            # Skip if target_config specified and this isn't it
            if target_config and config != target_config:
                continue
            
            if config not in config_settings:
                config_settings[config] = {}
            
            _get_configuration_settings(compile_settings, link_settings, config_settings[config], ns, config)
    
    # Write configuration-specific settings
    all_include_dirs = set()
    all_defines = {}
    all_force_includes = {}
    all_libraries = set()
    all_library_dirs = set()
    all_compile_options = {}
    all_link_options = {}
    all_runtime_libs = {}
    pch_settings = {}  # PCH settings per config
    all_output_files = {}  # OutputFile settings per config
    all_import_libraries = {}  # ImportLibrary settings per config
    all_pdb_files = {}  # PDB file settings per config
    
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
        
        if settings.get('library_dirs'):
            all_library_dirs.update(settings['library_dirs'])
        
        if settings.get('compile_options'):
            all_compile_options[config] = settings['compile_options']
        
        if settings.get('link_options'):
            all_link_options[config] = settings['link_options']
        
        if settings.get('runtime_library_flag'):
            all_runtime_libs[config] = settings['runtime_library_flag']
        
        # Collect output-related settings
        if settings.get('output_file'):
            all_output_files[config] = settings['output_file']
        
        if settings.get('import_library'):
            all_import_libraries[config] = settings['import_library']
        
        if settings.get('pdb_file'):
            all_pdb_files[config] = settings['pdb_file']
        
        # Collect PCH settings
        if settings.get('pch_use') and settings.get('pch_use') == 'Use':
            pch_header = settings.get('pch_header', 'stdafx.h')
            pch_settings[config] = {
                'use': True,
                'header': pch_header
            }
    
    # Add file-specific includes to the global set
    for file_includes in file_specific_includes.values():
        all_include_dirs.update(file_includes)
    
    # Add MFC define if using dynamic MFC - do this BEFORE processing defines
    mfc_defines = []
    if mfc_settings['use_afx_dll']:
        mfc_defines = ['_AFXDLL']
        print(f"  Adding _AFXDLL for dynamic MFC")
    
    # Check for Windows version defines and add defaults if missing
    # This is critical for modern Windows SDK headers that guard certain APIs
    # (like KSJACK_SINK_INFORMATION which requires Windows 7+)
    platform_toolset = get_platform_toolset(root, ns)
    win_version_defines = []
    
    # Collect all defines from all configurations to check
    all_defines_flat = []
    for config_defines in all_defines.values():
        all_defines_flat.extend(config_defines)
    
    win_version_defines = get_windows_version_defines(all_defines_flat, platform_toolset)
    if win_version_defines:
        print(f"  Adding Windows version defines: {', '.join(win_version_defines)}")
    
    # Determine PCH source file (the one that creates the PCH)
    pch_source_file = None
    pch_header_file = None
    files_not_using_pch = []
    
    # Check if any config uses PCH
    uses_pch = bool(pch_settings)
    
    if uses_pch:
        # Get PCH header from first config that has it
        for config, pch_info in pch_settings.items():
            if pch_info.get('header'):
                pch_header_file = pch_info['header']
                break
        
        if not pch_header_file:
            pch_header_file = 'stdafx.h'  # Default
        
        # Find the source file that creates the PCH (has PrecompiledHeader=Create)
        # and files that don't use PCH
        for file_path, options in file_specific_options.items():
            if options.get('pch_mode') == 'Create':
                pch_source_file = file_path
                print(f"  PCH source file (creates PCH): {pch_source_file}")
            elif options.get('pch_mode') == 'NotUsing':
                files_not_using_pch.append(file_path)
                print(f"  File not using PCH: {file_path}")
        
        # If no explicit Create file found, look for common PCH source file patterns
        if not pch_source_file:
            pch_base = pch_header_file.replace('.h', '').lower()
            for source in sources:
                source_lower = source.lower()
                source_name = source_lower.split('/')[-1].replace('.cpp', '')
                if source_name == pch_base or source_name == 'stdafx' or source_name == 'pch':
                    pch_source_file = source
                    print(f"  PCH source file (inferred): {pch_source_file}")
                    break
        
        print(f"  Precompiled header: {pch_header_file}")
    
    # Write include directories (common to all configs or specific config)
    if all_include_dirs:
        cmake_content.append('')
        cmake_content.append(f'target_include_directories({project_name} PRIVATE')
        for inc_dir in sorted(all_include_dirs):
            cmake_content.append(f'    {inc_dir}')
        cmake_content.append(')')
    
    # Write library directories
    if all_library_dirs:
        cmake_content.append('')
        cmake_content.append('# Additional library directories')
        cmake_content.append(f'# Note: CMake target dependencies handle most library paths automatically')
        cmake_content.append(f'target_link_directories({project_name} PRIVATE')
        for lib_dir in sorted(all_library_dirs):
            # Skip common build output directories that CMake will handle
            if '/lib/public' not in lib_dir.lower() and '/lib/common' not in lib_dir.lower():
                cmake_content.append(f'    {lib_dir}')
        cmake_content.append(')')
    
    # Write configuration-specific defines
    if all_defines or mfc_defines or win_version_defines:
        cmake_content.append('')
        if target_config:
            # If specific config, write directly without generator expressions
            cmake_content.append(f'target_compile_definitions({project_name} PRIVATE')
            # Add Windows version defines first (most important for header compatibility)
            for define in win_version_defines:
                # Don't quote simple defines - CMake handles them fine
                cmake_content.append(f'    {define}')
            # Add MFC defines
            for define in mfc_defines:
                cmake_content.append(f'    {define}')
            # Then add other defines
            for defines in all_defines.values():
                for define in defines:
                    # Quote defines that contain special characters or paths
                    if '\\' in define or ' ' in define or '"' in define:
                        cmake_content.append(f'    "{define}"')
                    else:
                        cmake_content.append(f'    {define}')
            cmake_content.append(')')
        else:
            # Multi-config: use generator expressions
            cmake_content.append(f'target_compile_definitions({project_name} PRIVATE')
            # Add Windows version defines unconditionally (they apply to all configs)
            for define in win_version_defines:
                cmake_content.append(f'    {define}')
            # Add MFC defines unconditionally (they apply to all configs)
            for define in mfc_defines:
                cmake_content.append(f'    {define}')
            # Then add config-specific defines
            for config in sorted(all_defines.keys()):
                defines = all_defines[config]
                # For generator expressions, we need to be careful with quoting
                define_parts = []
                for d in defines:
                    if '\\' in d or ' ' in d or '"' in d:
                        define_parts.append(f'"{d}"')
                    else:
                        define_parts.append(d)
                define_str = ';'.join(define_parts)
                cmake_content.append(f'    $<$<CONFIG:{config}>:{define_str}>')
            cmake_content.append(')')
    
    # Write force includes
    if all_force_includes:
        cmake_content.append('')
        cmake_content.append('# Force includes')
        if target_config:
            # If specific config, write directly
            cmake_content.append(f'target_compile_options({project_name} PRIVATE')
            for includes in all_force_includes.values():
                for include in includes:
                    cmake_content.append(f'    /FI{include}')
            cmake_content.append(')')
        else:
            # Multi-config: use generator expressions
            cmake_content.append(f'target_compile_options({project_name} PRIVATE')
            for config in sorted(all_force_includes.keys()):
                includes = all_force_includes[config]
                for include in includes:
                    cmake_content.append(f'    $<$<CONFIG:{config}>:/FI{include}>')
            cmake_content.append(')')
    
    # Write compiler options (optimization, warnings, SIMD, etc.)
    # Note: Windows version defines are added as /D flags here (in addition to compile_definitions)
    # because /D flags in compile_options are processed before PCH includes, which is critical
    # for headers like devicetopology.h that check _WIN32_WINNT at inclusion time.
    win_version_compile_opts = [f'/D{d}' for d in win_version_defines] if win_version_defines else []
    
    if all_compile_options or win_version_compile_opts:
        cmake_content.append('')
        cmake_content.append('# Compiler options')
        if target_config:
            # If specific config, write directly
            cmake_content.append(f'target_compile_options({project_name} PRIVATE')
            # Add Windows version defines first as /D flags for PCH compatibility
            for opt in win_version_compile_opts:
                cmake_content.append(f'    {opt}')
            for opts in all_compile_options.values():
                for opt in opts:
                    cmake_content.append(f'    {opt}')
            cmake_content.append(')')
        else:
            # Multi-config: use generator expressions
            cmake_content.append(f'target_compile_options({project_name} PRIVATE')
            # Add Windows version defines unconditionally
            for opt in win_version_compile_opts:
                cmake_content.append(f'    {opt}')
            for config in sorted(all_compile_options.keys()):
                opts = all_compile_options[config]
                for opt in opts:
                    cmake_content.append(f'    $<$<CONFIG:{config}>:{opt}>')
            cmake_content.append(')')
    
    # Write runtime library settings (using MSVC_RUNTIME_LIBRARY property)
    if all_runtime_libs and not mfc_settings['use_mfc']:
        # MFC projects already set runtime library, so skip if MFC is used
        cmake_content.append('')
        cmake_content.append('# Runtime library configuration')
        if target_config and target_config in all_runtime_libs:
            rt_flag = all_runtime_libs[target_config]
            # Map MSVC flags to CMake MSVC_RUNTIME_LIBRARY values
            rt_map = {
                '/MT': 'MultiThreaded',
                '/MTd': 'MultiThreadedDebug', 
                '/MD': 'MultiThreadedDLL',
                '/MDd': 'MultiThreadedDebugDLL'
            }
            if rt_flag in rt_map:
                cmake_content.append(f'set_property(TARGET {project_name} PROPERTY')
                cmake_content.append(f'    MSVC_RUNTIME_LIBRARY "{rt_map[rt_flag]}")')
        else:
            # Multi-config: determine the pattern from available configs
            has_debug = 'Debug' in all_runtime_libs
            has_release = 'Release' in all_runtime_libs
            
            debug_rt = all_runtime_libs.get('Debug', '/MTd')
            release_rt = all_runtime_libs.get('Release', '/MT')
            
            # Determine if using static or DLL runtime
            if '/MD' in debug_rt or '/MD' in release_rt:
                cmake_content.append(f'set_property(TARGET {project_name} PROPERTY')
                cmake_content.append('    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")')
            else:
                cmake_content.append(f'set_property(TARGET {project_name} PROPERTY')
                cmake_content.append('    MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")')
    
    # Write linker options
    if all_link_options:
        cmake_content.append('')
        cmake_content.append('# Linker options')
        if target_config:
            # If specific config, write directly
            cmake_content.append(f'target_link_options({project_name} PRIVATE')
            for opts in all_link_options.values():
                for opt in opts:
                    cmake_content.append(f'    {opt}')
            cmake_content.append(')')
        else:
            # Multi-config: use generator expressions
            cmake_content.append(f'target_link_options({project_name} PRIVATE')
            for config in sorted(all_link_options.keys()):
                opts = all_link_options[config]
                for opt in opts:
                    cmake_content.append(f'    $<$<CONFIG:{config}>:{opt}>')
            cmake_content.append(')')
    
    # Write output settings (OutputFile, ImportLibrary, OutDir, etc.)
    has_output_settings = (all_output_files or all_import_libraries or output_settings or global_target_name)
    
    if has_output_settings:
        cmake_content.append('')
        cmake_content.append('# Output settings')
        
        # Helper function to expand VS macros for CMake
        def expand_vs_macros(path, config=None, use_generator_expr=False):
            """
            Expand Visual Studio macros to CMake equivalents.
            
            Args:
                path: The path containing VS macros
                config: The configuration name (e.g., 'Debug', 'Release')
                use_generator_expr: If True, use $<CONFIG> for $(Configuration) 
                                   instead of literal config name
            """
            if not path:
                return path
            result = path
            # $(OutDir) -> CMAKE_RUNTIME_OUTPUT_DIRECTORY or similar
            result = result.replace('$(OutDir)', '${CMAKE_CURRENT_BINARY_DIR}')
            result = result.replace('$(IntDir)', '${CMAKE_CURRENT_BINARY_DIR}')
            result = result.replace('$(TargetDir)', '${CMAKE_CURRENT_BINARY_DIR}/')
            result = result.replace('$(TargetName)', '${PROJECT_NAME}')
            result = result.replace('$(ProjectDir)', '${CMAKE_CURRENT_SOURCE_DIR}/')
            result = result.replace('$(SolutionDir)', '${CMAKE_SOURCE_DIR}/')
            
            # Handle $(Configuration) - use generator expression for multi-config,
            # or literal value for single-config
            if use_generator_expr:
                result = result.replace('$(Configuration)', '$<CONFIG>')
            else:
                result = result.replace('$(Configuration)', config if config else '${CMAKE_BUILD_TYPE}')
            
            result = result.replace('$(Platform)', '${CMAKE_GENERATOR_PLATFORM}')
            # Clean up double slashes
            while '//' in result:
                result = result.replace('//', '/')
            # Clean up any double CMAKE_SOURCE_DIR references
            while '${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/' in result:
                result = result.replace('${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/', '${CMAKE_SOURCE_DIR}/')
            while '${CMAKE_CURRENT_SOURCE_DIR}/${CMAKE_CURRENT_SOURCE_DIR}/' in result:
                result = result.replace('${CMAKE_CURRENT_SOURCE_DIR}/${CMAKE_CURRENT_SOURCE_DIR}/', '${CMAKE_CURRENT_SOURCE_DIR}/')
            return result
        
        def has_configuration_macro(path):
            """Check if path contains $(Configuration) macro"""
            return path and '$(Configuration)' in path
        
        # Helper to extract just the filename from a path
        def get_output_name(output_file_path):
            """Extract the output name from a full path"""
            if not output_file_path:
                return None
            # Get just the filename
            filename = output_file_path.split('/')[-1]
            # Remove extension
            if '.' in filename:
                return filename.rsplit('.', 1)[0]
            return filename
        
        # Determine if we need to set OUTPUT_NAME (if it differs from project_name)
        output_name = None
        if global_target_name and global_target_name != project_name:
            output_name = global_target_name
        elif all_output_files:
            # Get output name from OutputFile setting
            for config, output_file in all_output_files.items():
                extracted_name = get_output_name(output_file)
                if extracted_name and extracted_name != project_name:
                    output_name = extracted_name
                    break
        
        # Set OUTPUT_NAME if different from target name
        if output_name:
            cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
            cmake_content.append(f'    OUTPUT_NAME "{output_name}"')
            cmake_content.append(')')
            print(f"  Output name: {output_name}")
        
        # Set output directories from PropertyGroup settings
        out_dirs_by_config = {}
        paths_have_config_macro = False
        
        for config, settings in output_settings.items():
            if settings.get('out_dir'):
                raw_path = settings['out_dir']
                if has_configuration_macro(raw_path):
                    paths_have_config_macro = True
                out_dir = expand_vs_macros(raw_path, config)
                # Remove trailing slashes and dots
                out_dir = out_dir.rstrip('/').rstrip('.')
                if out_dir:
                    out_dirs_by_config[config] = out_dir
        
        if out_dirs_by_config:
            # Check if all configs use the same output directory pattern
            # If paths only differ because of $(Configuration), they're effectively the same pattern
            unique_dirs = set(out_dirs_by_config.values())
            
            # If paths contained $(Configuration), use generator expression version
            if paths_have_config_macro:
                # Get any config's raw path and expand with generator expression
                any_config = next(iter(output_settings.keys()))
                if output_settings[any_config].get('out_dir'):
                    out_dir = expand_vs_macros(output_settings[any_config]['out_dir'], 
                                               any_config, use_generator_expr=True)
                    # Clean up the path
                    out_dir = out_dir.rstrip('/').rstrip('.')
                    if out_dir.endswith('/.'):
                        out_dir = out_dir[:-2]
                    cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
                    if is_lib and 'StaticLibrary' in project_type:
                        cmake_content.append(f'    ARCHIVE_OUTPUT_DIRECTORY "{out_dir}"')
                    elif is_lib:  # Shared library
                        cmake_content.append(f'    LIBRARY_OUTPUT_DIRECTORY "{out_dir}"')
                        cmake_content.append(f'    RUNTIME_OUTPUT_DIRECTORY "{out_dir}"  # For Windows DLLs')
                    else:  # Executable
                        cmake_content.append(f'    RUNTIME_OUTPUT_DIRECTORY "{out_dir}"')
                    cmake_content.append(')')
                    print(f"  Output directory: {out_dir}")
            elif len(unique_dirs) == 1:
                # Same directory for all configs
                out_dir = list(unique_dirs)[0]
                # Clean up the path
                out_dir = out_dir.rstrip('/').rstrip('.')
                if out_dir.endswith('/.'):
                    out_dir = out_dir[:-2]
                cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
                if is_lib and 'StaticLibrary' in project_type:
                    cmake_content.append(f'    ARCHIVE_OUTPUT_DIRECTORY "{out_dir}"')
                elif is_lib:  # Shared library
                    cmake_content.append(f'    LIBRARY_OUTPUT_DIRECTORY "{out_dir}"')
                    cmake_content.append(f'    RUNTIME_OUTPUT_DIRECTORY "{out_dir}"  # For Windows DLLs')
                else:  # Executable
                    cmake_content.append(f'    RUNTIME_OUTPUT_DIRECTORY "{out_dir}"')
                cmake_content.append(')')
            else:
                # Different directories per config - use generator expressions
                cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
                for config, out_dir in sorted(out_dirs_by_config.items()):
                    # Clean up the path
                    out_dir = out_dir.rstrip('/').rstrip('.')
                    if out_dir.endswith('/.'):
                        out_dir = out_dir[:-2]
                    if is_lib and 'StaticLibrary' in project_type:
                        cmake_content.append(f'    ARCHIVE_OUTPUT_DIRECTORY_{config.upper()} "{out_dir}"')
                    elif is_lib:
                        cmake_content.append(f'    LIBRARY_OUTPUT_DIRECTORY_{config.upper()} "{out_dir}"')
                        cmake_content.append(f'    RUNTIME_OUTPUT_DIRECTORY_{config.upper()} "{out_dir}"')
                    else:
                        cmake_content.append(f'    RUNTIME_OUTPUT_DIRECTORY_{config.upper()} "{out_dir}"')
                cmake_content.append(')')
        
        # Set import library location for DLLs
        if all_import_libraries and is_lib and 'DynamicLibrary' in project_type:
            import_lib_dirs = {}
            import_lib_names = {}
            import_lib_has_config_macro = False
            
            for config, import_lib_path in all_import_libraries.items():
                if has_configuration_macro(import_lib_path):
                    import_lib_has_config_macro = True
                expanded = expand_vs_macros(import_lib_path, config)
                # Extract directory and filename
                if '/' in expanded:
                    dir_part = '/'.join(expanded.split('/')[:-1])
                    name_part = expanded.split('/')[-1]
                    if name_part.endswith('.lib'):
                        name_part = name_part[:-4]
                    import_lib_dirs[config] = dir_part
                    import_lib_names[config] = name_part
            
            if import_lib_dirs:
                unique_dirs = set(import_lib_dirs.values())
                
                if import_lib_has_config_macro:
                    # Use generator expression for $(Configuration)
                    any_config = next(iter(all_import_libraries.keys()))
                    raw_path = all_import_libraries[any_config]
                    expanded = expand_vs_macros(raw_path, any_config, use_generator_expr=True)
                    if '/' in expanded:
                        imp_dir = '/'.join(expanded.split('/')[:-1])
                        imp_dir = imp_dir.rstrip('/').rstrip('.')
                        if imp_dir.endswith('/.'):
                            imp_dir = imp_dir[:-2]
                        cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
                        cmake_content.append(f'    ARCHIVE_OUTPUT_DIRECTORY "{imp_dir}"  # Import library location')
                        cmake_content.append(')')
                        print(f"  Import library directory: {imp_dir}")
                elif len(unique_dirs) == 1:
                    imp_dir = list(unique_dirs)[0]
                    # Clean up path
                    imp_dir = imp_dir.rstrip('/').rstrip('.')
                    if imp_dir.endswith('/.'):
                        imp_dir = imp_dir[:-2]
                    cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
                    cmake_content.append(f'    ARCHIVE_OUTPUT_DIRECTORY "{imp_dir}"  # Import library location')
                    cmake_content.append(')')
                    print(f"  Import library directory: {imp_dir}")
                else:
                    cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
                    for config, imp_dir in sorted(import_lib_dirs.items()):
                        imp_dir = imp_dir.rstrip('/').rstrip('.')
                        if imp_dir.endswith('/.'):
                            imp_dir = imp_dir[:-2]
                        cmake_content.append(f'    ARCHIVE_OUTPUT_DIRECTORY_{config.upper()} "{imp_dir}"')
                    cmake_content.append(')')
        
        # Set PDB output location
        if all_pdb_files:
            pdb_dirs = {}
            pdb_has_config_macro = False
            for config, pdb_path in all_pdb_files.items():
                if has_configuration_macro(pdb_path):
                    pdb_has_config_macro = True
                expanded = expand_vs_macros(pdb_path, config)
                if '/' in expanded:
                    pdb_dir = '/'.join(expanded.split('/')[:-1])
                    pdb_dirs[config] = pdb_dir
            
            if pdb_dirs:
                unique_dirs = set(pdb_dirs.values())
                
                if pdb_has_config_macro:
                    # Use generator expression for $(Configuration)
                    any_config = next(iter(all_pdb_files.keys()))
                    raw_path = all_pdb_files[any_config]
                    expanded = expand_vs_macros(raw_path, any_config, use_generator_expr=True)
                    if '/' in expanded:
                        pdb_dir = '/'.join(expanded.split('/')[:-1])
                        cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
                        cmake_content.append(f'    PDB_OUTPUT_DIRECTORY "{pdb_dir}"')
                        cmake_content.append(')')
                elif len(unique_dirs) == 1:
                    pdb_dir = list(unique_dirs)[0]
                    cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
                    cmake_content.append(f'    PDB_OUTPUT_DIRECTORY "{pdb_dir}"')
                    cmake_content.append(')')
                else:
                    cmake_content.append(f'set_target_properties({project_name} PROPERTIES')
                    for config, pdb_dir in sorted(pdb_dirs.items()):
                        cmake_content.append(f'    PDB_OUTPUT_DIRECTORY_{config.upper()} "{pdb_dir}"')
                    cmake_content.append(')')
    
    # Write libraries
    if all_libraries:
        cmake_content.append('')
        cmake_content.append(f'target_link_libraries({project_name} PRIVATE')
        
        # Separate system libraries from project libraries
        system_libs = []
        project_libs = []
        solution_target_libs = []  # Libraries that are solution projects - use target_link_libraries
        absolute_path_libs = []  # Libraries with absolute paths that need manual fixing
        
        # Helper to check if lib is a solution project
        def check_solution_project(lib_name):
            """Check if library name matches a solution project (case-insensitive).
            Returns the correct CMake target name if found, None otherwise."""
            sanitized = lib_name.replace('-', '_').replace(' ', '_').replace('(', '_').replace(')', '_')
            sanitized_lower = sanitized.lower()
            
            # Debug: print what we're looking for
            # print(f"    DEBUG check_solution_project: lib_name='{lib_name}', sanitized_lower='{sanitized_lower}'")
            # print(f"    DEBUG solution_projects_lower keys: {list(solution_projects_lower.keys())[:10]}...")
            
            # Check case-insensitive match
            if sanitized_lower in solution_projects_lower:
                return solution_projects_lower[sanitized_lower]
            
            lib_lower = lib_name.lower()
            if lib_lower in solution_projects_lower:
                return solution_projects_lower[lib_lower]
            
            return None
        
        for lib in sorted(all_libraries):
            # Normalize path separators
            lib_normalized = lib.replace('\\\\', '/').replace('\\', '/')
            
            # Check if it's an absolute Windows path (e.g., F:/Github/...)
            is_absolute_path = (len(lib_normalized) > 2 and lib_normalized[1] == ':') or lib_normalized.startswith('/')
            
            if is_absolute_path:
                # Absolute path - add to a separate list for warnings
                lib_name = Path(lib_normalized).stem
                if lib_name not in absolute_path_libs:
                    absolute_path_libs.append({
                        'name': lib_name,
                        'path': lib_normalized
                    })
                    print(f"  WARNING: Absolute path in AdditionalDependencies: {lib_normalized}")
                continue
            
            # Skip libraries that look like they're referencing build output directories
            # These will be handled by CMake target dependencies
            if '../lib/' in lib_normalized.lower() or 'release/' in lib_normalized.lower() or 'debug/' in lib_normalized.lower():
                continue
            
            # Check if it's a full path to a .lib file
            if '.lib' in lib_normalized.lower():
                # Check if it's a relative path (project library)
                if '../' in lib_normalized or './' in lib_normalized or lib_normalized.startswith('lib/'):
                    # Project library with relative path - skip, will be handled by target dependencies
                    continue
                else:
                    # Could be just a filename like "tier0.lib" - remove extension
                    lib_name = lib_normalized
                    if lib_name.lower().endswith('.lib'):
                        lib_name = lib_name[:-4]
                    
                    # Check if this is a solution project - link as CMake target
                    target_name = check_solution_project(lib_name)
                    if target_name:
                        if target_name not in solution_target_libs:
                            solution_target_libs.append(target_name)
                            print(f"  Library '{lib_name}' is a solution project - linking as target: {target_name}")
                    # Check if it's a Windows system library
                    elif lib_name.lower() in ['kernel32', 'user32', 'gdi32', 'winspool', 'shell32', 
                                            'ole32', 'oleaut32', 'uuid', 'comdlg32', 'advapi32',
                                            'ws2_32', 'winmm', 'version', 'odbc32', 'odbccp32',
                                            'opengl32', 'glu32', 'wsock32', 'iphlpapi', 'psapi',
                                            'dbghelp', 'rpcrt4', 'wininet', 'urlmon']:
                        system_libs.append(lib_name)
                    else:
                        # Probably a project library target name - try to find correct case
                        # Even though check_solution_project didn't find it, it might still be
                        # a solution project with slightly different naming
                        project_libs.append(lib_name)
            else:
                # No .lib extension, treat as library name
                # Check if this is a solution project first
                target_name = check_solution_project(lib)
                if target_name:
                    if target_name not in solution_target_libs:
                        solution_target_libs.append(target_name)
                        print(f"  Library '{lib}' is a solution project - linking as target: {target_name}")
                elif lib.lower() in ['kernel32', 'user32', 'gdi32', 'winspool', 'shell32', 
                                   'ole32', 'oleaut32', 'uuid', 'comdlg32', 'advapi32',
                                   'ws2_32', 'winmm', 'version', 'odbc32', 'odbccp32',
                                   'opengl32', 'glu32', 'wsock32', 'iphlpapi', 'psapi',
                                   'dbghelp', 'rpcrt4', 'wininet', 'urlmon']:
                    system_libs.append(lib)
                else:
                    project_libs.append(lib)
        
        # Write solution project targets first (proper CMake target dependencies)
        for lib in solution_target_libs:
            cmake_content.append(f'    {lib}')
        # Then other project libraries
        for lib in project_libs:
            cmake_content.append(f'    {lib}')
        # Finally system libraries
        for lib in system_libs:
            cmake_content.append(f'    {lib}')
        
        cmake_content.append(')')
        
        # Handle absolute path libraries - commented out with instructions
        if absolute_path_libs:
            cmake_content.append('')
            cmake_content.append('# WARNING: The following libraries had absolute paths in AdditionalDependencies.')
            cmake_content.append('# You need to either:')
            cmake_content.append('#   1. Copy the library to your project and use a relative path')
            cmake_content.append('#   2. Set up a CMake variable for the library location')
            cmake_content.append('#   3. Use find_library() to locate it')
            cmake_content.append(f'# target_link_libraries({project_name} PRIVATE')
            for lib_info in absolute_path_libs:
                cmake_content.append(f'#     "{lib_info["path"]}"  # {lib_info["name"]}')
            cmake_content.append('# )')
    
    # Get project references
    project_refs = []
    for ref in root.findall('.//ns:ProjectReference', ns):
        if 'Include' in ref.attrib:
            dep_path = Path(ref.attrib['Include'])
            dep_name = dep_path.stem
            # Sanitize the name to match CMake target naming
            sanitized_dep_name = dep_name.replace('-', '_').replace(' ', '_').replace('(', '_').replace(')', '_')
            
            # Look up the correct case from solution projects
            dep_lower = sanitized_dep_name.lower()
            if dep_lower in solution_projects_lower:
                # Use the correct case from the solution
                project_refs.append(solution_projects_lower[dep_lower])
            else:
                # Fallback to sanitized name if not found in solution
                project_refs.append(sanitized_dep_name)
    
    # Get static library references (from <Library> elements in ItemGroup)
    library_refs = []  # Project libraries (targets)
    external_libs = []  # External libraries (need full path or library dir)
    
    # Libraries that should be treated as CMake targets (built by this solution)
    # This is populated from the solution_projects parameter which contains all
    # project names in the solution (now a dict: lowercase -> proper case)
    known_cmake_targets = solution_projects_lower.copy() if solution_projects_lower else {}
    
    # Helper to check if a library name matches a solution project
    def is_solution_project(lib_name):
        """Check if a library name matches any project in the solution (case-insensitive).
        Returns the correct CMake target name if found, None otherwise."""
        # Sanitize the library name the same way project names are sanitized
        sanitized = lib_name.replace('-', '_').replace(' ', '_').replace('(', '_').replace(')', '_')
        sanitized_lower = sanitized.lower()
        
        # Check case-insensitive match
        if sanitized_lower in solution_projects_lower:
            return solution_projects_lower[sanitized_lower]
        
        lib_lower = lib_name.lower()
        if lib_lower in solution_projects_lower:
            return solution_projects_lower[lib_lower]
        
        return None
    
    def convert_lib_path_to_cmake(lib_path, original_path=None):
        """
        Convert a library path to the appropriate CMake path variable.
        
        - Paths starting with ../ go to parent directories -> ${CMAKE_SOURCE_DIR}/
        - Paths in the current directory (no ../) -> ${CMAKE_CURRENT_SOURCE_DIR}/
        - Paths already containing ${CMAKE_SOURCE_DIR} are not modified
        - Absolute paths are returned as-is
        
        Args:
            lib_path: The normalized library path (with forward slashes)
            original_path: The original path before normalization (for reference)
            
        Returns:
            Tuple of (cmake_path, is_local) where is_local is True if the path
            is relative to the current source directory
        """
        # Skip if already a CMake variable path
        if '${CMAKE_SOURCE_DIR}' in lib_path or '${CMAKE_CURRENT_SOURCE_DIR}' in lib_path:
            # Clean up any double variable references like ${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/
            while '${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/' in lib_path:
                lib_path = lib_path.replace('${CMAKE_SOURCE_DIR}/${CMAKE_SOURCE_DIR}/', '${CMAKE_SOURCE_DIR}/')
            while '${CMAKE_CURRENT_SOURCE_DIR}/${CMAKE_CURRENT_SOURCE_DIR}/' in lib_path:
                lib_path = lib_path.replace('${CMAKE_CURRENT_SOURCE_DIR}/${CMAKE_CURRENT_SOURCE_DIR}/', '${CMAKE_CURRENT_SOURCE_DIR}/')
            return lib_path, False
        
        # Check if it's an absolute Windows path (e.g., F:/Github/...)
        is_absolute = (len(lib_path) > 2 and lib_path[1] == ':') or lib_path.startswith('/')
        if is_absolute:
            return lib_path, False
        
        # Check if path goes to parent directory (starts with ../)
        if lib_path.startswith('../'):
            # Path goes outside current directory - use CMAKE_SOURCE_DIR
            # Count how many ../ we need to skip and only use CMAKE_SOURCE_DIR once
            # We remove all leading ../ and prepend CMAKE_SOURCE_DIR
            path_parts = lib_path.split('/')
            # Skip all leading .. parts
            non_parent_start = 0
            for i, part in enumerate(path_parts):
                if part == '..':
                    non_parent_start = i + 1
                else:
                    break
            # Reconstruct path with CMAKE_SOURCE_DIR
            remaining_path = '/'.join(path_parts[non_parent_start:])
            cmake_path = '${CMAKE_SOURCE_DIR}/' + remaining_path
            # Clean up any double slashes
            while '//' in cmake_path:
                cmake_path = cmake_path.replace('//', '/')
            return cmake_path, False
        
        # Path is local to the current directory - use CMAKE_CURRENT_SOURCE_DIR
        # Strip leading ./ if present
        clean_path = lib_path.lstrip('./')
        cmake_path = '${CMAKE_CURRENT_SOURCE_DIR}/' + clean_path
        # Clean up any double slashes
        while '//' in cmake_path:
            cmake_path = cmake_path.replace('//', '/')
        return cmake_path, True
    
    for lib_item in root.findall('.//ns:ItemGroup/ns:Library', ns):
        if 'Include' in lib_item.attrib:
            lib_path = lib_item.attrib['Include'].replace('\\', '/')
            lib_file = Path(lib_path).stem
            
            # Sanitize the library name for CMake
            sanitized_lib_file = lib_file.replace('-', '_').replace(' ', '_').replace('(', '_').replace(')', '_')
            
            # Filter out known non-library names (directories, etc.)
            skip_names = ['steam', 'wintab']
            if lib_file.lower() in skip_names:
                print(f"  Skipping non-library reference: {lib_file}")
                continue
            
            # Categorize the library based on its path
            lib_path_lower = lib_path.lower()
            lib_file_lower = lib_file.lower()
            
            # FIRST: Check if this is a project in our solution - if so, always link by target name
            target_name = is_solution_project(lib_file)
            if target_name:
                if target_name not in library_refs and target_name not in project_refs:
                    library_refs.append(target_name)
                    print(f"  Found solution project dependency: {lib_file} -> target: {target_name}")
                continue
            
            # Check for lib/public in path (handle relative paths like ../lib/public/)
            is_in_lib_public = '/lib/public/' in lib_path_lower or 'lib/public/' in lib_path_lower
            
            # Check for lib/common in path
            is_in_lib_common = '/lib/common/' in lib_path_lower or 'lib/common/' in lib_path_lower
            
            if is_in_lib_public or is_in_lib_common:
                # Pre-built library - link by path
                cmake_path, is_local = convert_lib_path_to_cmake(lib_path)
                
                if lib_file not in [e['name'] for e in external_libs]:
                    external_libs.append({
                        'name': lib_file,
                        'path': cmake_path,
                        'original_path': lib_path,
                        'type': 'public' if is_in_lib_public else 'common',
                        'is_local': is_local
                    })
                    print(f"  Found pre-built library: {lib_file} -> {cmake_path}")
                    
            elif '/dx9sdk/' in lib_path_lower or '/dx10sdk/' in lib_path_lower or 'dx9sdk/' in lib_path_lower or 'dx10sdk/' in lib_path_lower:
                # DirectX SDK library
                cmake_path, is_local = convert_lib_path_to_cmake(lib_path)
                    
                if lib_file not in [e['name'] for e in external_libs]:
                    external_libs.append({
                        'name': lib_file,
                        'path': cmake_path,
                        'original_path': lib_path,
                        'type': 'dx_sdk',
                        'is_local': is_local
                    })
                    print(f"  Found DirectX SDK library: {lib_file}")
                    
            elif '.lib' in lib_path_lower:
                # Other external library with explicit path
                # Check if it's an absolute Windows path (e.g., F:\Github\...)
                is_absolute_path = (len(lib_path) > 2 and lib_path[1] == ':') or lib_path.startswith('/')
                
                if is_absolute_path:
                    # Absolute path - warn and comment out, or try to make relative
                    print(f"  WARNING: Absolute path library reference: {lib_path}")
                    if lib_file not in [e['name'] for e in external_libs]:
                        external_libs.append({
                            'name': lib_file,
                            'path': lib_path,  # Keep original path
                            'original_path': lib_path,
                            'type': 'absolute_path',  # Special type for absolute paths
                            'is_local': False
                        })
                else:
                    cmake_path, is_local = convert_lib_path_to_cmake(lib_path)
                    
                    if lib_file not in [e['name'] for e in external_libs]:
                        external_libs.append({
                            'name': lib_file,
                            'path': cmake_path,
                            'original_path': lib_path,
                            'type': 'other',
                            'is_local': is_local
                        })
                        print(f"  Found external library: {lib_file} at {cmake_path}")
            else:
                # Unknown - treat as CMake target
                # Look up the correct case from solution projects
                target_name = is_solution_project(lib_file)
                if target_name:
                    if target_name not in library_refs and target_name not in project_refs:
                        library_refs.append(target_name)
                        print(f"  Found library reference (solution project): {lib_file} -> {target_name}")
                elif lib_file not in library_refs and lib_file not in project_refs:
                    library_refs.append(lib_file)
                    print(f"  Found library reference (assuming CMake target): {lib_file}")
    
    # Combine project dependencies and library references
    all_deps = project_refs + library_refs
    
    if all_deps:
        cmake_content.append('')
        cmake_content.append('# Project dependencies (CMake targets from this solution)')
        cmake_content.append(f'target_link_libraries({project_name} PRIVATE')
        for ref in all_deps:
            cmake_content.append(f'    {ref}')
        cmake_content.append(')')
    
    # Add external libraries (with paths)
    if external_libs:
        cmake_content.append('')
        cmake_content.append('# Pre-built/external libraries')
        cmake_content.append(f'target_link_libraries({project_name} PRIVATE')
        
        # Group by type for better organization
        dx_libs = [e for e in external_libs if e['type'] == 'dx_sdk']
        public_libs = [e for e in external_libs if e['type'] == 'public']
        common_libs = [e for e in external_libs if e['type'] == 'common']
        other_libs = [e for e in external_libs if e['type'] == 'other']
        absolute_libs = [e for e in external_libs if e['type'] == 'absolute_path']
        
        # Further separate 'other' libs into local and parent directory libs
        local_other_libs = [e for e in other_libs if e.get('is_local', False)]
        parent_other_libs = [e for e in other_libs if not e.get('is_local', False)]
        
        if dx_libs:
            cmake_content.append('    # DirectX SDK')
            for lib in dx_libs:
                cmake_content.append(f'    "{lib["path"]}"')
        
        if public_libs:
            cmake_content.append('    # Pre-built libraries from lib/public')
            for lib in public_libs:
                cmake_content.append(f'    "{lib["path"]}"')
        
        if common_libs:
            cmake_content.append('    # Third-party libraries from lib/common')
            for lib in common_libs:
                cmake_content.append(f'    "{lib["path"]}"')
        
        if local_other_libs:
            cmake_content.append('    # Local external libraries (in project directory)')
            for lib in local_other_libs:
                cmake_content.append(f'    "{lib["path"]}"')
        
        if parent_other_libs:
            cmake_content.append('    # Other external libraries')
            for lib in parent_other_libs:
                cmake_content.append(f'    "{lib["path"]}"')
        
        cmake_content.append(')')
        
        # Handle absolute path libraries separately - commented out with instructions
        if absolute_libs:
            cmake_content.append('')
            cmake_content.append('# WARNING: The following libraries had absolute paths in the vcxproj.')
            cmake_content.append('# You need to either:')
            cmake_content.append('#   1. Copy the library to your project and use a relative path')
            cmake_content.append('#   2. Set up a CMake variable for the library location')
            cmake_content.append('#   3. Use find_library() to locate it')
            cmake_content.append(f'# target_link_libraries({project_name} PRIVATE')
            for lib in absolute_libs:
                cmake_content.append(f'#     "{lib["path"]}"  # Original: {lib["original_path"]}')
            cmake_content.append('# )')
    
    # Mark excluded files with HEADER_FILE_ONLY property so they appear in IDE but don't compile
    if excluded_sources or excluded_headers:
        cmake_content.append('')
        cmake_content.append('# Exclude files from build (but keep them visible in IDE)')
        all_excluded = excluded_sources + excluded_headers
        if all_excluded:
            cmake_content.append('set_source_files_properties(')
            for excluded_file in all_excluded:
                cmake_content.append(f'    {excluded_file}')
            cmake_content.append('    PROPERTIES')
            cmake_content.append('    HEADER_FILE_ONLY TRUE')
            cmake_content.append(')')
    
    # Configure precompiled headers
    if uses_pch and pch_header_file:
        cmake_content.append('')
        cmake_content.append('# Precompiled header configuration')
        cmake_content.append(f'# PCH Header: {pch_header_file}')
        
        if pch_source_file:
            cmake_content.append(f'# PCH Source: {pch_source_file}')
        
        # For MSVC, use /Yu and /Yc flags directly - this is more reliable than target_precompile_headers
        # because it matches exactly what Visual Studio does
        cmake_content.append('if(MSVC)')
        
        # Check if current source directory or "." is already in include dirs
        # Visual Studio implicitly includes the project directory, CMake does not
        current_dir_in_includes = any(
            inc_dir in ['.', './', '${CMAKE_CURRENT_SOURCE_DIR}', '${CMAKE_CURRENT_SOURCE_DIR}/']
            for inc_dir in all_include_dirs
        )
        
        if not current_dir_in_includes:
            # Add current source directory so the PCH header can be found
            cmake_content.append(f'    # Add project directory to includes (VS does this implicitly for PCH)')
            cmake_content.append(f'    target_include_directories({project_name} PRIVATE')
            cmake_content.append(f'        ${{CMAKE_CURRENT_SOURCE_DIR}}')
            cmake_content.append('    )')
        
        # If there are files that don't use PCH, we can't use global /FI
        # Instead, we need to handle PCH per-file or use a different approach
        if files_not_using_pch:
            # Set /Yu (use precompiled header) globally but NOT /FI
            # Files that use PCH will get /FI individually
            cmake_content.append(f'    # Note: /FI is not set globally because some files don\'t use PCH')
            cmake_content.append(f'    target_compile_options({project_name} PRIVATE')
            cmake_content.append(f'        /Yu"{pch_header_file}"')
            cmake_content.append('    )')
            
            # Set /Yc (create precompiled header) for the PCH source file
            # The PCH source needs both /Yc and /FI
            if pch_source_file:
                cmake_content.append(f'    set_source_files_properties({pch_source_file} PROPERTIES')
                cmake_content.append(f'        COMPILE_FLAGS "/Yc\\"{pch_header_file}\\" /FI\\"{pch_header_file}\\""')
                cmake_content.append('    )')
            
            cmake_content.append('endif()')
            
            # Files that DON'T use PCH need /Y- to disable PCH completely
            cmake_content.append('')
            cmake_content.append('# Files that do not use precompiled headers')
            cmake_content.append('if(MSVC)')
            cmake_content.append('    set_source_files_properties(')
            for file_path in files_not_using_pch:
                cmake_content.append(f'        {file_path}')
            cmake_content.append('        PROPERTIES')
            cmake_content.append('        COMPILE_FLAGS "/Y-"  # Disable PCH for these files')
            cmake_content.append('    )')
            cmake_content.append('endif()')
            
            # Files that DO use PCH (all source files except PCH source and non-PCH files) need /FI
            pch_source_lower = pch_source_file.lower() if pch_source_file else ''
            files_not_using_pch_lower = [f.lower() for f in files_not_using_pch]
            files_using_pch = []
            for src in sources:
                src_lower = src.lower()
                if src_lower != pch_source_lower and src_lower not in files_not_using_pch_lower:
                    files_using_pch.append(src)
            
            if files_using_pch:
                cmake_content.append('')
                cmake_content.append('# Files that use precompiled headers need /FI to force include the PCH')
                cmake_content.append('if(MSVC)')
                cmake_content.append('    set_source_files_properties(')
                for file_path in files_using_pch:
                    cmake_content.append(f'        {file_path}')
                cmake_content.append('        PROPERTIES')
                cmake_content.append(f'        COMPILE_FLAGS "/FI\\"{pch_header_file}\\""')
                cmake_content.append('    )')
                cmake_content.append('endif()')
        else:
            # No files excluded from PCH - use simple global approach
            # Set /Yu (use precompiled header) for all source files
            cmake_content.append(f'    target_compile_options({project_name} PRIVATE')
            cmake_content.append(f'        /Yu"{pch_header_file}"')
            cmake_content.append(f'        /FI"{pch_header_file}"  # Force include the PCH header')
            cmake_content.append('    )')
            
            # Set /Yc (create precompiled header) for the PCH source file
            if pch_source_file:
                cmake_content.append(f'    set_source_files_properties({pch_source_file} PROPERTIES')
                cmake_content.append(f'        COMPILE_FLAGS "/Yc\\"{pch_header_file}\\""')
                cmake_content.append('    )')
            
            cmake_content.append('endif()')
    
    # Set file-specific compiler options
    if file_specific_options:
        cmake_content.append('')
        cmake_content.append('# File-specific compiler options')
        
        for file_path, options in file_specific_options.items():
            props = []
            compile_opts = []
            compile_defs = []
            
            # Handle CompileAs
            if options['compile_as']:
                compile_as = options['compile_as']
                if compile_as == 'CompileAsC':
                    props.append('    LANGUAGE C')
                elif compile_as == 'CompileAsCpp':
                    props.append('    LANGUAGE CXX')
                elif compile_as == 'Default':
                    pass  # Use project default
            
            # Handle RuntimeLibrary (MFC/CRT settings)
            if options['runtime_library']:
                rt_lib = options['runtime_library']
                # MultiThreaded = /MT, MultiThreadedDebug = /MTd
                # MultiThreadedDLL = /MD, MultiThreadedDebugDLL = /MDd
                if rt_lib == 'MultiThreaded':
                    compile_opts.append('/MT')
                elif rt_lib == 'MultiThreadedDebug':
                    compile_opts.append('/MTd')
                elif rt_lib == 'MultiThreadedDLL':
                    compile_opts.append('/MD')
                elif rt_lib == 'MultiThreadedDebugDLL':
                    compile_opts.append('/MDd')
            
            # Handle WarningLevel
            if options['warning_level']:
                warn_level = options['warning_level']
                if warn_level == 'Level1':
                    compile_opts.append('/W1')
                elif warn_level == 'Level2':
                    compile_opts.append('/W2')
                elif warn_level == 'Level3':
                    compile_opts.append('/W3')
                elif warn_level == 'Level4':
                    compile_opts.append('/W4')
                elif warn_level == 'TurnOffAllWarnings':
                    compile_opts.append('/W0')
            
            # Handle PreprocessorDefinitions
            if options['preprocessor_defs']:
                compile_defs = options['preprocessor_defs']
            
            # Write properties if any exist
            if props or compile_opts or compile_defs:
                cmake_content.append(f'set_source_files_properties({file_path}')
                cmake_content.append('    PROPERTIES')
                
                for prop in props:
                    cmake_content.append(prop)
                
                if compile_opts:
                    opts_str = ' '.join(compile_opts)
                    cmake_content.append(f'    COMPILE_OPTIONS "{opts_str}"')
                
                if compile_defs:
                    # Use a single COMPILE_DEFINITIONS with semicolon-separated list
                    defs_str = ';'.join(compile_defs)
                    cmake_content.append(f'    COMPILE_DEFINITIONS "{defs_str}"')
                
                cmake_content.append(')')
    
    # Return the cmake content and project info instead of writing directly
    # This allows multiple projects to be combined in one CMakeLists.txt
    all_deps = project_refs + library_refs
    return {
        'content': cmake_content,
        'project_name': project_name,
        'is_library': is_lib,
        'project_type': project_type,
        'dependencies': all_deps
    }


def write_cmake_file(vcxproj_path, cmake_result):
    """Write a single project's CMake content to file"""
    output_dir = Path(vcxproj_path).parent
    with open(output_dir / 'CMakeLists.txt', 'w') as f:
        f.write('\n'.join(cmake_result['content']))
        f.write('\n')


def write_combined_cmake_file(output_dir, cmake_results, same_dir_projects):
    """
    Write multiple projects' CMake content to a single file.
    
    Args:
        output_dir: Directory to write CMakeLists.txt
        cmake_results: List of cmake result dicts from convert_vcxproj
        same_dir_projects: Dict mapping project names to their info for dependency resolution
    """
    combined_content = []
    
    # Add comment header
    combined_content.append('# Combined CMakeLists.txt for multiple projects in this directory')
    combined_content.append(f'# Projects: {", ".join(r["project_name"] for r in cmake_results)}')
    combined_content.append('')
    
    # Build a map of project names for dependency detection
    local_project_names = {r['project_name'] for r in cmake_results}
    
    # Sort projects: libraries first, then executables
    # Also need to sort by dependency order within libraries
    libs = [r for r in cmake_results if r['is_library']]
    exes = [r for r in cmake_results if not r['is_library']]
    
    # Sort libraries by dependencies (simple topological sort)
    def sort_by_deps(projects):
        """Sort projects so dependencies come first"""
        sorted_projects = []
        remaining = list(projects)
        sorted_names = set()
        
        max_iterations = len(remaining) * 2  # Prevent infinite loop
        iteration = 0
        
        while remaining and iteration < max_iterations:
            iteration += 1
            made_progress = False
            
            for proj in remaining[:]:  # Iterate over copy
                deps = set(proj.get('dependencies', []))
                # Check if all local dependencies are already sorted
                local_deps = deps & local_project_names
                if local_deps <= sorted_names:
                    sorted_projects.append(proj)
                    sorted_names.add(proj['project_name'])
                    remaining.remove(proj)
                    made_progress = True
            
            # If no progress made, there might be circular deps - just add remaining
            if not made_progress:
                sorted_projects.extend(remaining)
                break
        
        return sorted_projects
    
    libs = sort_by_deps(libs)
    exes = sort_by_deps(exes)
    
    ordered_results = libs + exes
    
    for result in ordered_results:
        project_name = result['project_name']
        content = result['content']
        
        combined_content.append(f'# {"="*60}')
        combined_content.append(f'# Project: {project_name}')
        if result['is_library']:
            combined_content.append(f'# Type: Library ({result["project_type"]})')
        else:
            combined_content.append(f'# Type: Executable')
        
        # Show dependencies
        deps = result.get('dependencies', [])
        local_deps = [d for d in deps if d in local_project_names]
        if local_deps:
            combined_content.append(f'# Local dependencies: {", ".join(local_deps)}')
        
        combined_content.append(f'# {"="*60}')
        combined_content.append('')
        
        # Add all content lines
        combined_content.extend(content)
        combined_content.append('')
        combined_content.append('')
    
    # Write the combined file
    with open(output_dir / 'CMakeLists.txt', 'w') as f:
        f.write('\n'.join(combined_content))
        f.write('\n')
    
    print(f"  Wrote combined CMakeLists.txt with {len(cmake_results)} projects")
    for result in ordered_results:
        dep_note = ""
        local_deps = [d for d in result.get('dependencies', []) if d in local_project_names]
        if local_deps:
            dep_note = f" (depends on: {', '.join(local_deps)})"
        proj_type = "library" if result['is_library'] else "executable"
        print(f"    - {result['project_name']} ({proj_type}){dep_note}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert Visual Studio Project to CMake')
    parser.add_argument('vcxproj_path', help='Path to the .vcxproj file')
    parser.add_argument('--config', '-c', dest='config', help='Target configuration (e.g., Debug, Release)')
    
    args = parser.parse_args()
    result = convert_vcxproj(args.vcxproj_path, args.config)
    write_cmake_file(args.vcxproj_path, result)

if __name__ == '__main__':
    main()