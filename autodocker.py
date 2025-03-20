import yaml
import os
from pprint import pprint
from threading import Thread, Lock
import subprocess
from datetime import datetime
import sys
import argparse
from queue import Queue, Empty
from platform_utils import can_build_platform, process_requirements_cmd
from io import StringIO
from tqdm import tqdm

class AutoDockerConfig:
    """
    Manages configuration for AutoDocker builds.
    
    This class handles loading and validating the YAML configuration,
    and provides easy access to configuration values.
    """
    def __init__(self, config_file):
        """
        Initialize configuration from YAML file.
        
        Args:
            config_file (str): Path to YAML configuration file
        
        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config file is invalid YAML
        """
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self):
        """Load and validate configuration file."""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
                
            # Validate required sections
            required_sections = ['platforms', 'project']
            missing = [s for s in required_sections if s not in config]
            if missing:
                raise ValueError(f"Missing required sections in config: {', '.join(missing)}")
                
            return config
            
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file '{self.config_file}' not found")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML file: {e}")
    
    @property
    def platforms(self):
        """Get list of platform configurations."""
        return self.config['platforms']
    
    @property
    def project(self):
        """Get project configuration."""
        return self.config['project']
    
    @property
    def cmake_info(self):
        """Get CMake configuration."""
        return self.config.get('cmake')
    
    @property
    def cmake_versions(self):
        """Get list of CMake versions to build against."""
        if self.cmake_info:
            return self.cmake_info.get('versions', [])
        return []
    
    @property
    def qemu_info(self):
        """Get QEMU configuration."""
        return self.config.get('qemu')
    
    @property
    def python_info(self):
        """Get Python configuration."""
        return self.config.get('python')
    
    @property
    def ssh_config(self):
        """Get SSH configuration."""
        return self.config.get('ssh-keys')
    
    def get_dependencies(self):
        """Get all dependency configurations."""
        return {
            'python': self.python_info,
            'qemu': self.qemu_info,
            'aocl-utils': self.config.get('aocl-utils')
        }
    
    def get_platform_cmake_versions(self, platform):
        """
        Get CMake versions for a specific platform.
        
        Args:
            platform (dict): Platform configuration
        
        Returns:
            list: List of CMake versions or [None] if CMake not required
        """
        return self.cmake_versions if 'cmake' in platform.get('depends', []) else [None]

def read_yaml_config(file_path):
    """
    Read and parse a YAML configuration file.
    
    Args:
        file_path (str): Path to the YAML configuration file
    
    Returns:
        dict: Parsed YAML configuration
    """
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

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
RUN {process_requirements_cmd(platform)}
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

def prefix_output(line, prefix):
    """
    Add prefix to each line of output.
    
    Args:
        line (str): Line of output
        prefix (str): Prefix to add
    
    Returns:
        str: Prefixed output line
    """
    return f"[{prefix}] {line}"

def run_command(cmd, logfile, container_name="", verbose=False):
    """
    Run a shell command and log its output.
    
    Args:
        cmd (str): Command to execute
        logfile (str): Path to log file
        container_name (str, optional): Container name for output prefixing
        verbose (bool, optional): Enable verbose output
    
    Returns:
        int: Command exit code
    """
    print_manager = PrintManager()
    with open(logfile, 'w', buffering=1) as f:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        for line in process.stdout:
            # Write original line to log file
            f.write(line)
            f.flush()
            
            if verbose:
                # Add prefix for console output
                prefixed_line = prefix_output(line.rstrip(), container_name)
                print_manager.direct_print(prefixed_line)
        
        process.wait()
        return process.returncode

class PrintManager:
    """
    Thread-safe print manager for coordinated console output.
    
    Handles synchronized printing with progress bar management
    and provides various printing utilities.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PrintManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize the singleton instance"""
        self.print_queue = Queue()
        self.is_running = True
        self.progress_manager = None
        self.printer_thread = Thread(target=self._printer_worker)
        self.printer_thread.daemon = True
        self.printer_thread.start()
        self.lock = Lock()

    def set_progress_manager(self, progress_manager):
        """Set the progress manager instance"""
        self.progress_manager = progress_manager

    def _printer_worker(self):
        while self.is_running or not self.print_queue.empty():
            try:
                message = self.print_queue.get(timeout=0.1)
                with self.lock:
                    if self.progress_manager:
                        # Clear progress bar, print message, restore progress bar
                        self.progress_manager.clear()
                        sys.stdout.write(message + '\n')
                        sys.stdout.flush()
                        self.progress_manager.refresh()
                    else:
                        sys.stdout.write(message + '\n')
                        sys.stdout.flush()
                self.print_queue.task_done()
            except Empty:
                continue
            except Exception as e:
                sys.stderr.write(f"Printer thread error: {e}\n")
                sys.stderr.flush()

    def print(self, message):
        """Print a message"""
        self.print_queue.put(str(message))

    def direct_print(self, message):
        """Immediately print a message with progress bar handling"""
        with self.lock:
            if self.progress_manager:
                self.progress_manager.clear()
                sys.stdout.write(message + '\n')
                sys.stdout.flush()
                self.progress_manager.refresh()
            else:
                sys.stdout.write(message + '\n')
                sys.stdout.flush()

    def separator(self):
        """Print a separator line"""
        self.print("\n" + "-" * 80)

    def pprint(self, obj):
        """Pretty print an object"""
        import pprint
        self.print(pprint.pformat(obj))

    def print_file(self, filepath):
        """Print contents of a file"""
        try:
            with open(filepath, 'r') as f:
                self.print(f.read())
        except Exception as e:
            self.print(f"Error reading file {filepath}: {e}")

    def stop(self):
        self.is_running = False
        if self.printer_thread.is_alive():
            self.printer_thread.join(timeout=1.0)

class ProgressManager:
    """
    Manages progress tracking for Docker operations.
    """
    STAGES = ['dockerfile', 'build', 'run', 'test', 'cleanup']
    
    def __init__(self, total_containers):
        """
        Initialize progress manager.
        
        Args:
            total_containers (int): Total number of containers to process
        """
        self.total_containers = total_containers
        self.current = 0
        self.progress_bar = tqdm(
            total=total_containers,
            desc="Processing containers",
            unit="container",
            position=0,
            leave=True,
            dynamic_ncols=True,
            bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] - {postfix}'
        )
        self.container_stages = {}
        self.lock = Lock()
    
    def update_stage(self, container_name, stage):
        """
        Update the stage of a container.
        
        Args:
            container_name (str): Name of the container
            stage (str): Current stage
        """
        with self.lock:
            if container_name not in self.container_stages:
                self.container_stages[container_name] = set()
            self.container_stages[container_name].add(stage)
            self.progress_bar.set_postfix_str(f"Container: {container_name} - Stage: {stage}")
    
    def increment(self):
        """Increment progress by one step."""
        with self.lock:
            self.current += 1
            self.progress_bar.update(1)
    
    def clear(self):
        """Clear the progress bar."""
        with self.lock:
            self.progress_bar.clear()
    
    def refresh(self):
        """Refresh the progress bar."""
        with self.lock:
            self.progress_bar.refresh()
    
    def close(self):
        """Close the progress bar."""
        with self.lock:
            self.progress_bar.close()

def write_failed_containers(status, print_manager):
    """
    Write information about failed containers to a file.
    
    Args:
        status (dict): Container status dictionary
        print_manager (PrintManager): Print manager instance
    """
    failed_containers = {
        container: {
            'status': info['status'],
            'image': info.get('image_name', 'unknown'),
            'debug_command': info.get('debug_command', '')
        }
        for container, info in status.items()
        if info['status'] != 'success'
    }
    
    if failed_containers:
        with open('failed_containers.txt', 'w') as f:
            f.write("Failed Containers Information:\n")
            f.write("============================\n\n")
            for container, info in failed_containers.items():
                f.write(f"Container: {container}\n")
                f.write(f"Status: {info['status']}\n")
                f.write(f"Image: {info['image']}\n")
                f.write(f"Debug Command: {info['debug_command']}\n")
                f.write("-" * 50 + "\n\n")
        
        print_manager.print(f"\nFailed containers information written to failed_containers.txt")
        print_manager.print("\nTo debug a failed container, use the debug command provided in failed_containers.txt")

class LogManager:
    """
    Manages log files for Docker operations.
    """
    def __init__(self, base_dir='logs'):
        """
        Initialize log manager.
        
        Args:
            base_dir (str): Base directory for logs
        """
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)
    
    def get_log_path(self, container_name, log_type):
        """
        Get path for a log file.
        
        Args:
            container_name (str): Name of the container
            log_type (str): Type of log (build, run, cleanup)
            
        Returns:
            tuple: (log_dir, log_file)
        """
        log_dir = os.path.join(self.base_dir, container_name)
        os.makedirs(log_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"{log_type}_{timestamp}.log")
        
        return log_dir, log_file
    
    def write_failed_containers(self, status, print_manager):
        """
        Write information about failed containers to a file.
        
        Args:
            status (dict): Status dictionary
            print_manager (PrintManager): Print manager for output
        """
        failed = [name for name, info in status.items() if info['status'] == 'build_failed']
        if failed:
            print_manager.print("\nFailed containers:")
            with open('failed_containers.txt', 'w') as f:
                for name in failed:
                    debug_cmd = f"docker run --rm -it --entrypoint /bin/bash {get_image_name_from_container(name)}"
                    print_manager.print(f"{name}: {debug_cmd}")
                    f.write(f"{name}: {debug_cmd}\n")
            print_manager.print("\nSee failed_containers.txt for debug commands")
            return True
        return False

class DockerManager:
    """
    Manages Docker operations including building and running containers.
    """
    def __init__(self, print_manager, progress_manager, log_manager, debug=False, verbose=False, keepfailed=False):
        """
        Initialize Docker manager.
        
        Args:
            print_manager (PrintManager): Print manager for output
            progress_manager (ProgressManager): Progress manager for tracking
            log_manager (LogManager): Log manager for file handling
            debug (bool): Enable debug mode
            verbose (bool): Enable verbose output
            keepfailed (bool): Keep failed containers
        """
        self.print_manager = print_manager
        self.progress_manager = progress_manager
        self.log_manager = log_manager
        self.debug = debug
        self.verbose = verbose
        self.keepfailed = keepfailed
    
    def cleanup_existing(self, container_name):
        """
        Clean up any existing container with the same name.
        
        Args:
            container_name (str): Name of the container to clean up
        """
        try:
            subprocess.run(
                f"docker rm -f {container_name}".split(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except:
            pass
    
    def build_image(self, dockerfile_path, image_name, container_name):
        """
        Build a Docker image.
        
        Args:
            dockerfile_path (str): Path to Dockerfile
            image_name (str): Name for the image
            container_name (str): Name for the container
            
        Returns:
            tuple: (success, log_file_path)
        """
        self.progress_manager.update_stage(container_name, 'build')
        
        # Get log file path
        _, log_file = self.log_manager.get_log_path(container_name, 'build')
        
        # Build command
        cmd = f"docker build -t {image_name} -f {dockerfile_path} ."
        if self.verbose:
            self.print_manager.print(f"\nBuilding {container_name}...")
            self.print_manager.print(f"Command: {cmd}")
        
        # Run build
        try:
            with open(log_file, 'w') as f:
                result = subprocess.run(
                    cmd.split(),
                    stdout=f if not self.verbose else subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode != 0:
                self.print_manager.print(f"\nBuild failed for {container_name}. See {log_file} for details.")
                if self.verbose:
                    self.print_manager.print(result.stdout)
                return False, log_file
                
            if self.verbose:
                self.print_manager.print(f"Build successful for {container_name}")
            return True, log_file
            
        except Exception as e:
            self.print_manager.print(f"\nError building {container_name}: {str(e)}")
            return False, log_file
    
    def run_container(self, image_name, container_name, project_info):
        """
        Run a Docker container.
        
        Args:
            image_name (str): Name of the image to run
            container_name (str): Name for the container
            project_info (dict): Project configuration
            
        Returns:
            tuple: (success, log_file_path)
        """
        self.progress_manager.update_stage(container_name, 'run')
        
        # Clean up any existing container
        self.cleanup_existing(container_name)
        
        # Get log file path
        _, log_file = self.log_manager.get_log_path(container_name, 'run')
        
        # Run command
        cmd = f"docker run --rm --name {container_name}"
        if project_info.get('test-cmd'):
            cmd = f"{cmd} {image_name} /bin/bash -c '{project_info['test-cmd']}'"
        else:
            cmd = f"{cmd} {image_name}"
            
        if self.verbose:
            self.print_manager.print(f"\nRunning {container_name}...")
            self.print_manager.print(f"Command: {cmd}")
        
        # Run container
        try:
            with open(log_file, 'w') as f:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    stdout=f if not self.verbose else subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                
            if result.returncode != 0:
                self.print_manager.print(f"\nRun failed for {container_name}. See {log_file} for details.")
                if self.verbose:
                    self.print_manager.print(result.stdout)
                    
                # Clean up on failure if not keeping failed containers
                if not self.keepfailed:
                    self.cleanup_container(container_name, image_name)
                return False, log_file
                
            if self.verbose:
                self.print_manager.print(f"Run successful for {container_name}")
            return True, log_file
            
        except Exception as e:
            self.print_manager.print(f"\nError running {container_name}: {str(e)}")
            if not self.keepfailed:
                self.cleanup_container(container_name, image_name)
            return False, log_file
    
    def cleanup_container(self, container_name, image_name):
        """
        Clean up a container and its image.
        
        Args:
            container_name (str): Name of the container
            image_name (str): Name of the image
        """
        try:
            # Remove container
            subprocess.run(
                f"docker rm -f {container_name}".split(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # Remove image
            subprocess.run(
                f"docker rmi -f {image_name}".split(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except:
            pass

class ContainerManager:
    """
    Manages container-specific operations and status tracking.
    """
    def __init__(self, container_name, image_name, dockerfile_path, project_info, status, status_lock):
        """
        Initialize container manager.
        
        Args:
            container_name (str): Name of the container
            image_name (str): Name of the image
            dockerfile_path (str): Path to Dockerfile
            project_info (dict): Project configuration
            status (dict): Shared status dictionary
            status_lock (Lock): Lock for status dictionary
        """
        self.container_name = container_name
        self.image_name = image_name
        self.dockerfile_path = dockerfile_path
        self.project_info = project_info
        self.status = status
        self.status_lock = status_lock
    
    def update_status(self, **kwargs):
        """
        Update container status.
        
        Args:
            **kwargs: Key-value pairs to update in status
        """
        with self.status_lock:
            if self.container_name not in self.status:
                self.status[self.container_name] = {}
            self.status[self.container_name].update(kwargs)
    
    def record_build_start(self):
        """Record build start in status."""
        self.update_status(
            status='building',
            image_name=self.image_name,
            debug_command=f"docker run --rm -it --entrypoint /bin/bash {self.image_name}"
        )
    
    def record_build_failure(self, build_log):
        """
        Record build failure in status.
        
        Args:
            build_log (str): Path to build log file
        """
        self.update_status(
            status='build_failed',
            code=125,
            build_log=build_log
        )
    
    def record_run_completion(self, success, run_log):
        """
        Record run completion in status.
        
        Args:
            success (bool): Whether the run was successful
            run_log (str): Path to run log file
        """
        self.update_status(
            status='success' if success else 'run_failed',
            code=0 if success else 1,
            run_log=run_log
        )
    
    def record_error(self, error):
        """
        Record error in status.
        
        Args:
            error (str): Error message
        """
        self.update_status(
            status='error',
            code=-1,
            error=str(error)
        )

def docker_worker(dockerfile_path, image_name, container_name, status, status_lock, print_manager, project_info, progress_manager, debug=False, verbose=False, keepfailed=False, ssh_config=None):
    """
    Worker function for building and running Docker containers.
    
    Args:
        dockerfile_path (str): Path to Dockerfile
        image_name (str): Name for the image
        container_name (str): Name for the container
        status (dict): Shared status dictionary
        status_lock (Lock): Lock for status dictionary
        print_manager (PrintManager): Print manager for output
        project_info (dict): Project configuration
        progress_manager (ProgressManager): Progress manager for tracking
        debug (bool): Enable debug mode
        verbose (bool): Enable verbose output
        keepfailed (bool): Keep failed containers
        ssh_config (dict): SSH configuration
    """
    log_manager = LogManager()
    docker = DockerManager(print_manager, progress_manager, log_manager, debug, verbose, keepfailed)
    container = ContainerManager(container_name, image_name, dockerfile_path, project_info, status, status_lock)
    
    try:
        # Record build start
        container.record_build_start()
        
        # Build image
        build_success, build_log = docker.build_image(dockerfile_path, image_name, container_name)
        
        if not build_success:
            container.record_build_failure(build_log)
            return
        
        # Run container
        run_success, run_log = docker.run_container(image_name, container_name, project_info)
        
        # Record run completion
        container.record_run_completion(run_success, run_log)
        
        if run_success:
            print_manager.print(f"\nContainer {container_name} succeeded. Logs at {run_log}")
        else:
            print_manager.print(f"\nContainer {container_name} failed. Logs at {run_log}")
            
    except Exception as e:
        container.record_error(e)
        print_manager.print(f"\nError processing {container_name}: {str(e)}")
    finally:
        progress_manager.increment()

def print_failure_logs(status, print_manager):
    """Print logs for failed builds/runs"""
    for container, result in status.items():
        if result['status'] != 'success':
            print_manager.print(f"\nFailure detected for {container}:")
            print_manager.print(f"Status: {result['status']}")
            print_manager.print(f"Exit code: {result['code']}")
            
            if 'build_log' in result:
                print_manager.print("\nBuild log:")
                print_manager.print_file(result['build_log'])
            
            if 'run_log' in result:
                print_manager.print("\nRun log:")
                print_manager.print_file(result['run_log'])

def sanitize_tag(tag):
    """
    Sanitize tag name to be compatible with Docker/Podman.
    
    Args:
        tag (str|int): Tag to sanitize
    
    Returns:
        str: Sanitized tag string
    """
    # Convert tag to string if it's a number
    tag = str(tag)
    return tag.replace('/', '-').replace(':', '-')

def sanitize_name(name):
    """
    Sanitize a name for use in Docker tags and container names.
    
    Args:
        name (str): Name to sanitize
        
    Returns:
        str: Sanitized name
    """
    return name.lower().replace(' ', '-')

def get_container_name(platform, cmake_version):
    """
    Generate a container name from platform and CMake version.
    
    Args:
        platform (dict): Platform configuration
        cmake_version (str): CMake version or None
        
    Returns:
        str: Container name
    """
    base_name = sanitize_name(platform['name'])
    version_suffix = f"-cmake-{cmake_version}" if cmake_version else ""
    return f"{base_name}{version_suffix}"

def get_image_name(platform, cmake_version):
    """
    Generate an image name from platform and CMake version.
    
    Args:
        platform (dict): Platform configuration
        cmake_version (str): CMake version or None
        
    Returns:
        str: Image name
    """
    platform_tag = sanitize_name(platform['version'] if platform['version'] != 'latest' else platform['image'])
    version_suffix = f"-cmake-{cmake_version}" if cmake_version else ""
    return f"{platform_tag}{version_suffix}"

def get_image_name_from_container(container_name):
    """
    Extract image name from container name.
    
    Args:
        container_name (str): Container name
        
    Returns:
        str: Image name
    """
    parts = container_name.split('-')
    if 'cmake' in parts:
        cmake_idx = parts.index('cmake')
        return '-'.join(parts[:cmake_idx] + parts[cmake_idx:])
    return container_name

class BuildManager:
    """
    Manages the build process for Docker containers.
    """
    def __init__(self, config, print_manager, debug=False, verbose=False, keepfailed=False):
        """
        Initialize build manager.
        
        Args:
            config (AutoDockerConfig): Configuration manager
            print_manager (PrintManager): Print manager for output
            debug (bool): Enable debug mode
            verbose (bool): Enable verbose output
            keepfailed (bool): Keep failed containers
        """
        self.config = config
        self.print_manager = print_manager
        self.debug = debug
        self.verbose = verbose
        self.keepfailed = keepfailed
        
        # Initialize status tracking
        self.status = {}
        self.status_lock = Lock()
        
        # Calculate total containers
        self.total_containers = sum(
            len(config.get_platform_cmake_versions(platform))
            for platform in config.platforms
            if can_build_platform(platform)
        )
        
        # Initialize managers
        self.progress_manager = ProgressManager(self.total_containers)
        self.print_manager.set_progress_manager(self.progress_manager)
        self.log_manager = LogManager()
        self.docker_manager = DockerManager(
            self.print_manager,
            self.progress_manager,
            self.log_manager,
            self.debug,
            self.verbose,
            self.keepfailed
        )
        
        # Create necessary directories
        os.makedirs('build', exist_ok=True)
        
        # Keep track of threads
        self.threads = []
    
    def process_platform(self, platform):
        """
        Process a single platform configuration.
        
        Args:
            platform (dict): Platform configuration
        """
        if not can_build_platform(platform):
            self.print_manager.print(f"Skipping platform {platform['name']} - requirements not met")
            return
        
        for cmake_version in self.config.get_platform_cmake_versions(platform):
            container_info = {
                'platform': platform,
                'cmake_version': cmake_version,
                'project': self.config.project,
                'dependencies': self.config.get_dependencies()
            }
            
            container_name = get_container_name(platform, cmake_version)
            dockerfile_path = create_dockerfile(
                container_info,
                ssh_config=self.config.ssh_config
            )
            
            thread = Thread(
                target=docker_worker,
                args=(
                    dockerfile_path,
                    get_image_name(platform, cmake_version),
                    container_name,
                    self.status,
                    self.status_lock,
                    self.print_manager,
                    self.config.project,
                    self.progress_manager,
                    self.debug,
                    self.verbose,
                    self.keepfailed,
                    self.config.ssh_config
                )
            )
            self.threads.append(thread)
            thread.start()
    
    def process_all_platforms(self):
        """Process all platform configurations."""
        try:
            # Process each platform
            for platform in self.config.platforms:
                self.process_platform(platform)
                
            # Wait for all threads to complete
            for thread in self.threads:
                thread.join()
                
            # Print final status
            self.print_manager.separator()
            self.print_manager.print("\nBuild Status:")
            self.print_manager.pprint(self.status)
            
            # Write failed containers information
            if self.log_manager.write_failed_containers(self.status, self.print_manager):
                return 1
                
            return 0
            
        except Exception as e:
            self.print_manager.print(f"Error: {str(e)}")
            return 1
        finally:
            # Clean up threads
            for thread in self.threads:
                if thread.is_alive():
                    thread.join(timeout=1)
            
            # Clean up progress manager
            if hasattr(self, 'progress_manager'):
                self.progress_manager.close()
            
            # Clean up print manager
            if hasattr(self, 'print_manager'):
                self.print_manager.stop()

def main():
    """
    Main function that orchestrates the Docker build process.
    
    Returns:
        int: 0 for success, 1 for failure
    """
    parser = argparse.ArgumentParser(description='Build Docker images for multiple platforms')
    parser.add_argument('-f', '--file', help='YAML configuration file', required=True)
    parser.add_argument('-v', '--verbose', help='Enable verbose output', action='store_true')
    parser.add_argument('-d', '--debug', help='Enable debug mode', action='store_true')
    parser.add_argument('-k', '--keepfailed', help='Keep failed containers', action='store_true')
    args = parser.parse_args()

    try:
        # Initialize configuration
        config = AutoDockerConfig(args.file)
        
        # Initialize print manager
        print_manager = PrintManager()
        
        # Initialize build manager
        build_manager = BuildManager(
            config,
            print_manager,
            args.debug,
            args.verbose,
            args.keepfailed
        )
        
        # Process all platforms
        return build_manager.process_all_platforms()
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
