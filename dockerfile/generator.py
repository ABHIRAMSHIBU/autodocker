import os
from utils.docker_utils import get_container_name

def get_base_setup(platform):
    """
    Generate base system setup commands for Dockerfile.
    
    Args:
        platform (dict): Platform configuration containing:
            - image (str): Base image name
            - version (str): Image version
            - update-cmd (str): System update command
    
    Returns:
        str: Dockerfile commands for base system setup
    """
    env_setup = 'ENV DEBIAN_FRONTEND=noninteractive' if platform['image'] == 'ubuntu' else ''
    return f"""FROM {platform['image']}:{platform['version']}
    
{env_setup}

# Update system
RUN {platform['update-cmd']}

# Install requirements
RUN {platform['requirements-cmd']}
"""

def get_cmake_setup(platform, cmake_info, cmake_version):
    """
    Generate CMake installation commands for Dockerfile.
    
    Args:
        platform (dict): Platform configuration
        cmake_info (dict): CMake configuration containing:
            - url (str): Download URL template
        cmake_version (str): CMake version to install
    
    Returns:
        str: Dockerfile commands for CMake installation or empty string if not needed
    """
    if 'cmake' not in platform.get('depends', []):
        return ""
    
    return f"""# Install CMake {cmake_version}
WORKDIR /tmp
RUN wget {cmake_info['url'].replace('<version>', cmake_version)}
RUN bash cmake-{cmake_version}-linux-x86_64.sh --skip-license --prefix=/usr/local
"""

def get_qemu_setup(platform, qemu_info):
    """
    Generate QEMU build and installation commands for Dockerfile.
    
    Args:
        platform (dict): Platform configuration
        qemu_info (dict): QEMU configuration containing:
            - url (str): Download URL
            - version (str): QEMU version
            - configure-cmd (str): Configuration command
            - build-cmd (str): Build command
            - install-cmd (str): Installation command
    
    Returns:
        str: Dockerfile commands for QEMU setup or empty string if not needed
    """
    if 'qemu' not in platform.get('depends', []):
        return ""
    
    return f"""# Build and Install QEMU
WORKDIR /tmp
RUN wget -4 {qemu_info['url'].replace('<version>', qemu_info['version'])}
RUN tar xf qemu-{qemu_info['version']}.tar.xz
WORKDIR /tmp/qemu-{qemu_info['version']}
RUN {qemu_info['configure-cmd']}
RUN {qemu_info['build-cmd']}
RUN {qemu_info['install-cmd']}
"""

def get_python_setup(platform, python_info):
    """
    Generate Python build and installation commands for Dockerfile.
    
    Args:
        platform (dict): Platform configuration
        python_info (dict): Python configuration containing:
            - url (str): Download URL
            - version (str): Python version
            - configure-cmd (str): Configuration command
            - build-cmd (str): Build command
            - install-cmd (str): Installation command
    
    Returns:
        str: Dockerfile commands for Python setup or empty string if not needed
    """
    if 'python' not in platform.get('depends', []):
        return ""
    
    return f"""# Build and Install Python
WORKDIR /tmp
RUN wget {python_info['url'].replace('<version>', python_info['version'])}
RUN tar xf Python-{python_info['version']}.tar.xz
WORKDIR /tmp/Python-{python_info['version']}
RUN {python_info['configure-cmd']}
RUN {python_info['build-cmd']}
RUN {python_info['install-cmd']}
"""

def get_project_setup(project_info):
    """
    Generate project build commands for Dockerfile.
    
    Args:
        project_info (dict): Project configuration containing:
            - git-url (str): Project repository URL
            - branch (str): Git branch to checkout
            - configure-cmd (str): Project configuration command
            - build-cmd (str): Build command
            - install-cmd (str): Installation command
            - test-cmd (str): Test command
    
    Returns:
        str: Dockerfile commands for project setup
    """
    return f"""# Clone and build project
WORKDIR /app
RUN git clone {project_info['git-url']} .
RUN git checkout {project_info['branch']}
RUN {project_info['configure-cmd']}
RUN {project_info['build-cmd']}
RUN {project_info['install-cmd']}
CMD {project_info['test-cmd']}
"""

def get_git_dependency_setup(dependency_info, dep_name):
    """
    Generate git dependency build and installation commands for Dockerfile.
    
    Args:
        dependency_info (dict): Dependency configuration containing:
            - url (str): Git repository URL
            - branch (str): Git branch
            - configure-cmd (str): Configuration command
            - build-cmd (str): Build command
            - install-cmd (str): Installation command
        dep_name (str): Name of the dependency
    
    Returns:
        str: Dockerfile commands for dependency setup
    """
    return f"""# Clone and build dependency {dep_name}
RUN mkdir -p /tmp/{dep_name}
WORKDIR /tmp/{dep_name}
RUN git clone {dependency_info['url']} .
RUN git checkout {dependency_info['branch']}
RUN {dependency_info['configure-cmd']}
RUN {dependency_info['build-cmd']}
RUN {dependency_info['install-cmd']}
"""

def get_ssh_setup(ssh_config):
    """
    Generate SSH key setup commands for Dockerfile.
    
    Args:
        ssh_config (dict): SSH configuration containing:
            - enabled (bool): Whether SSH is enabled
            - path (str): Path to SSH directory containing keys
            - keys (list): List of key files to copy
            - mount-type (str): How to handle keys ("copy" or "volume")
    
    Returns:
        list: List of Dockerfile commands for SSH setup
    """
    if not ssh_config.get('enabled', False):
        return []

    commands = []
    
    # Create .ssh directory with correct permissions
    commands.append("RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh")

    # Get the SSH directory path from config
    ssh_dir = ssh_config.get('path', 'ssh')

    # Copy SSH keys and config
    for key in ssh_config.get('keys', []):
        key_name = os.path.basename(key)
        commands.append(f"COPY {ssh_dir}/{key_name} /root/.ssh/{key_name}")

    # Set proper permissions for all files
    commands.append('RUN bash -c "chmod 600 /root/.ssh/*"')
    
    # Configure SSH to accept new host keys automatically for github.com
    commands.append('RUN mkdir -p /etc/ssh/ && echo "StrictHostKeyChecking accept-new" >> /etc/ssh/ssh_config')
    
    # Fix the IdentityFile path in the SSH config if it exists
    commands.append('RUN if [ -f "/root/.ssh/config" ]; then sed -i "s|~/.ssh/|/root/.ssh/|g" /root/.ssh/config; fi')
    
    # Add debug command to verify SSH setup
    commands.append('RUN bash -c "ls -la /root/.ssh/ && if [ -f /root/.ssh/config ]; then cat /root/.ssh/config; fi"')

    return commands

def create_dockerfile(container_info, ssh_config=None):
    """
    Create a Dockerfile for the given container configuration.
    
    Args:
        container_info (dict): Container configuration containing:
            - platform (dict): Platform configuration
            - cmake_version (str): CMake version or None
            - project (dict): Project configuration
            - dependencies (dict): Dependencies configuration
        ssh_config (dict): SSH configuration
        
    Returns:
        str: Path to the created Dockerfile
    """
    platform = container_info['platform']
    cmake_version = container_info['cmake_version']
    project = container_info['project']
    dependencies = container_info['dependencies']
    
    commands = []
    
    # Base image
    commands.append(f"FROM {platform['image']}:{platform['version']}")
    
    # Set environment variables
    commands.append("\n# Set environment variables")
    commands.append("ENV DEBIAN_FRONTEND=noninteractive")
    
    # Update system
    commands.append("\n# Update system")
    commands.append(f"RUN {platform['update-cmd']}")
    
    # Install requirements
    commands.append("\n# Install requirements")
    commands.append(f"RUN {platform['requirements-cmd']}")
    
    # Add CMake if required
    if cmake_version:
        commands.append("\n# Install CMake")
        commands.append(f"RUN wget https://github.com/Kitware/CMake/releases/download/v{cmake_version}/cmake-{cmake_version}-linux-x86_64.sh \\")
        commands.append("    -q -O /tmp/cmake-install.sh && \\")
        commands.append("    chmod u+x /tmp/cmake-install.sh && \\")
        commands.append("    mkdir /opt/cmake && \\")
        commands.append("    /tmp/cmake-install.sh --skip-license --prefix=/opt/cmake && \\")
        commands.append("    rm /tmp/cmake-install.sh && \\")
        commands.append('    ln -s /opt/cmake/bin/* /usr/local/bin/')
    
    # Add Python if required
    if 'python' in platform.get('depends', []):
        python_info = dependencies.get('python')
        if python_info:
            commands.append("\n# Install Python")
            if 'version' in python_info:
                commands.append(f"RUN wget {python_info['url'].replace('<version>', python_info['version'])} \\")
                commands.append("    -q -O /tmp/python.tar.xz && \\")
                commands.append("    tar -xf /tmp/python.tar.xz -C /tmp && \\")
                commands.append(f"    cd /tmp/Python-{python_info['version']} && \\")
                commands.append(f"    {python_info['configure-cmd']} && \\")
                commands.append(f"    {python_info['build-cmd']} && \\")
                commands.append(f"    {python_info['install-cmd']} && \\")
                commands.append("    cd / && rm -rf /tmp/python.tar.xz /tmp/Python-*")
    
    # Add QEMU if required
    if 'qemu' in platform.get('depends', []):
        qemu_info = dependencies.get('qemu')
        if qemu_info:
            commands.append("\n# Install QEMU")
            commands.append(f"RUN wget {qemu_info['url'].replace('<version>', qemu_info['version'])} \\")
            commands.append("    -q -O /tmp/qemu.tar.xz && \\")
            commands.append("    tar -xf /tmp/qemu.tar.xz -C /tmp && \\")
            commands.append(f"    cd /tmp/qemu-{qemu_info['version']} && \\")
            commands.append(f"    {qemu_info['configure-cmd']} && \\")
            commands.append(f"    {qemu_info['build-cmd']} && \\")
            commands.append(f"    {qemu_info['install-cmd']} && \\")
            commands.append("    cd / && rm -rf /tmp/qemu.tar.xz /tmp/qemu-*")
    
    # Add SSH setup if required
    if ssh_config and ssh_config.get('enabled', False):
        commands.extend(get_ssh_setup(ssh_config))
    
    # Create working directory
    commands.append(f"\n# Create working directory")
    commands.append(f"WORKDIR /workspace")
    
    # Add project setup
    if project.get('git-url'):
        commands.append("\n# Clone project")
        commands.append(f"RUN git clone {project['git-url']} . && \\")
        if project.get('branch'):
            commands.append(f"    git checkout {project['branch']} && \\")
        if project.get('configure-cmd'):
            commands.append(f"    {project['configure-cmd']} && \\")
        if project.get('build-cmd'):
            commands.append(f"    {project['build-cmd']}")
    
    # Write Dockerfile
    container_name = get_container_name(platform, cmake_version)
    dockerfile_path = f"build/Dockerfile.{container_name}"
    
    with open(dockerfile_path, 'w') as f:
        f.write('\n'.join(commands))
    
    return dockerfile_path 