# AutoDocker Project Architecture

## Overview
AutoDocker is a Python-based tool for automating Docker container builds across multiple platforms and configurations. It supports building and testing projects with different dependencies (CMake, Python, QEMU) across various Linux distributions.

## Project Structure
```
autodocker/
├── managers/               # Core management components
│   ├── __init__.py
│   ├── print_manager.py   # Console output management
│   ├── progress_manager.py # Build progress tracking
│   ├── log_manager.py     # Log file handling
│   ├── docker_manager.py  # Docker operations
│   └── container_manager.py # Container status tracking
├── utils/                 # Utility functions and classes
│   ├── __init__.py
│   ├── config.py         # YAML configuration handling
│   ├── docker_utils.py   # Docker naming utilities
│   └── platform_utils.py # Platform compatibility checks
├── dockerfile/           # Dockerfile generation
│   ├── __init__.py
│   └── generator.py     # Dockerfile creation logic
└── autodocker.py       # Main script
```

## Core Components

### 1. Configuration Management
- **AutoDockerConfig** (`utils/config.py`)
  - Loads and validates YAML configuration files
  - Provides access to platform, project, and dependency configurations
  - Handles CMake, Python, QEMU, and SSH configurations
  - Properties:
    - `platforms`: List of platform configurations
    - `project`: Project build settings
    - `cmake_info`, `python_info`, `qemu_info`: Dependency configurations
    - `ssh_config`: SSH key settings

### 2. Manager Classes

#### PrintManager (`managers/print_manager.py`)
- Manages console output with progress bar integration
- Methods:
  - `print()`: Print messages while handling progress bar
  - `pprint()`: Pretty print objects
  - `print_file()`: Print file contents
  - `separator()`: Print separator lines

#### ProgressManager (`managers/progress_manager.py`)
- Tracks build progress using tqdm
- Features:
  - Multi-threaded progress tracking
  - Stage updates for each container
  - Thread-safe operations

#### LogManager (`managers/log_manager.py`)
- Handles log file management
- Features:
  - Organized log directory structure
  - Build and run logs for each container
  - Failed container tracking

#### DockerManager (`managers/docker_manager.py`)
- Manages Docker operations
- Features:
  - Image building
  - Container running
  - Cleanup operations
  - Verbose logging options

#### ContainerManager (`managers/container_manager.py`)
- Manages container-specific operations
- Features:
  - Status tracking
  - Thread-safe status updates
  - Build and run state management

### 3. Dockerfile Generation
- **Generator Module** (`dockerfile/generator.py`)
  - Functions for generating Dockerfile components:
    - `get_base_setup()`: Base image and system updates
    - `get_cmake_setup()`: CMake installation
    - `get_qemu_setup()`: QEMU build and install
    - `get_python_setup()`: Python build and install
    - `get_project_setup()`: Project clone and build
    - `get_ssh_setup()`: SSH configuration
  - Main function: `create_dockerfile()`

### 4. Utility Functions
- **Docker Utilities** (`utils/docker_utils.py`)
  - Name sanitization
  - Container and image naming
  - Tag management

- **Platform Utilities** (`utils/platform_utils.py`)
  - Platform compatibility checks
  - Requirements processing

## Threading Model
- Multi-threaded container builds
- Thread-safe components:
  - Status tracking with locks
  - Progress updates
  - Log file handling
  - Console output

## Build Process Flow
1. Load and validate configuration
2. Calculate total containers to build
3. Initialize managers
4. For each platform:
   - Check compatibility
   - For each CMake version:
     - Generate Dockerfile
     - Create build thread
     - Track progress
5. Wait for all builds to complete
6. Generate final status report
7. Clean up resources

## Configuration Files
Supports two types of YAML configurations:
1. Project Configuration:
   - Platform definitions
   - Build requirements
   - Dependency versions
   - Project settings

2. SSH Configuration (Optional):
   - SSH key management
   - Key mounting options
   - GitHub/GitLab access

## Error Handling
- Comprehensive error tracking
- Build and run failure logging
- Debug command generation
- Failed container preservation option

## Future Improvements
1. Enhanced platform compatibility checks
2. More dependency types support
3. Parallel dependency building
4. Remote build capabilities
5. Cache optimization
6. Network isolation options
7. Resource usage monitoring
8. Test result aggregation
9. CI/CD integration helpers
10. Container health checks 