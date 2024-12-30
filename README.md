# SLN to CMake Converter

A Python tool that converts Visual Studio Solution (*.sln) files to CMake build system.

## Features

- Converts Visual Studio Solution (*.sln) files to CMake
- Handles static libraries and executables
- Supports precompiled headers (PCH)
- Preserves project dependencies
- Handles force includes (even handles per configuration variants)
- Converts preprocessor definitions
- Maintains library linking
- Supports C++ standards configuration

## NOTE
- This tool is not meant to be a easy solution for complex projects, you eventually have to modify it for your projects.

## Requirements

- Python 3.6+
- CMake 3.16+ (for PCH support)

## Usage

Simply run the script with the path to your .sln file:

```bash
python sln2cmake.py path/to/your.sln
```

The script will create a CMakeLists.txt file in the same directory as your .sln file.

### Example

```bash
# Convert the example project
python sln2cmake.py TestProject/TestProject.sln
```

## Features in Detail

### 1. Project Structure
- Automatically detects project types (static libraries, executables)
- Maintains project dependencies and build order

### 2. Build Configuration
- Handles Debug/Release configurations
- Supports precompiled headers (PCH)
- Preserves force includes with configuration-specific variants
- Maintains preprocessor definitions

### 3. Library Management
- Links static libraries
- Preserves external library dependencies
- Maintains include directories

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.