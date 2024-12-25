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

def read_yaml_config(file_path):
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def get_base_setup(platform):
    """Generate base system setup commands"""
    env_setup = 'ENV DEBIAN_FRONTEND=noninteractive' if platform['image'] == 'ubuntu' else ''
    return f"""FROM {platform['image']}:{platform['version']}
    
{env_setup}

# Update system
RUN {platform['update-cmd']}

# Install requirements
RUN {process_requirements_cmd(platform)}
"""

def get_cmake_setup(platform, cmake_info, cmake_version):
    """Generate CMake installation if needed"""
    if 'cmake' not in platform.get('depends', []):
        return ""
    
    return f"""# Install CMake {cmake_version}
WORKDIR /tmp
RUN wget {cmake_info['url'].replace('<version>', cmake_version)}
RUN bash cmake-{cmake_version}-linux-x86_64.sh --skip-license --prefix=/usr/local
"""

def get_qemu_setup(platform, qemu_info):
    """Generate QEMU build and installation if needed"""
    if 'qemu' not in platform.get('depends', []):
        return ""
    
    return f"""# Build and Install QEMU
WORKDIR /tmp
RUN wget {qemu_info['url'].replace('<version>', qemu_info['version'])}
RUN tar xf qemu-{qemu_info['version']}.tar.xz
WORKDIR /tmp/qemu-{qemu_info['version']}
RUN {qemu_info['configure-cmd']}
RUN {qemu_info['build-cmd']}
RUN {qemu_info['install-cmd']}
"""

def get_python_setup(platform, python_info):
    """Generate Python build and installation if needed"""
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
    """Generate project build commands"""
    return f"""# Clone and build project
WORKDIR /app
RUN git clone {project_info['git-url']} .
RUN git checkout {project_info['branch']}
RUN {project_info['configure-cmd']}
RUN {project_info['build-cmd']}
RUN {project_info['install-cmd']}
CMD {project_info['test-cmd']}
"""

def create_dockerfile(platform, cmake_info, project_info, qemu_info, python_info, cmake_version):
    """Combine all Dockerfile sections"""
    sections = [
        get_base_setup(platform),
        get_python_setup(platform, python_info),
        get_qemu_setup(platform, qemu_info),
        get_cmake_setup(platform, cmake_info, cmake_version),
        get_project_setup(project_info)
    ]
    return "\n".join(sections)

def prefix_output(line, prefix):
    """Add prefix to each line of output"""
    return f"[{prefix}] {line}"

def run_command(cmd, logfile, container_name="", verbose=False):
    """Run a command and log its output"""
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
    STAGES = {
        'dockerfile': 'Creating Dockerfile',
        'build': 'Building Image',
        'run': 'Starting Container',
        'test': 'Running Tests',
        'cleanup': 'Cleanup'
    }
    
    def __init__(self, total_containers):
        self.total_containers = total_containers
        self.total_steps = total_containers * len(self.STAGES)
        self.progress_bar = tqdm(
            total=self.total_steps,
            desc="Overall Progress",
            unit="step",
            position=0,
            leave=True,
            dynamic_ncols=True,
            bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] - {postfix}',
        )
        self.current_stage = {}  # container_name -> set of completed stages
        self.lock = Lock()
    
    def update_stage(self, container_name, stage):
        """Update progress with new stage"""
        with self.lock:
            if container_name not in self.current_stage:
                self.current_stage[container_name] = set()
            
            if stage in self.STAGES and stage not in self.current_stage[container_name]:
                self.progress_bar.set_postfix_str(f"Container: {container_name} - Stage: {self.STAGES[stage]}")
                self.progress_bar.update(1)
                self.current_stage[container_name].add(stage)
    
    def clear(self):
        """Clear the progress bar"""
        with self.lock:
            self.progress_bar.clear()
    
    def refresh(self):
        """Refresh the progress bar"""
        with self.lock:
            self.progress_bar.refresh()
    
    def close(self):
        self.progress_bar.close()

def write_failed_containers(status, print_manager):
    """Write failed container information to a file"""
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

def docker_worker(dockerfile_path, image_name, container_name, status, status_lock, 
                 print_manager, project_info, progress_manager, debug=False, verbose=False, keepfailed=False):
    """Worker function to handle Docker build and run operations"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = os.path.join('logs', container_name)
        os.makedirs(log_dir, exist_ok=True)
        
        # Build Docker image from parent directory to include scripts
        build_log = os.path.join(log_dir, f'build_{timestamp}.log')
        build_cmd = f"docker buildx build -f {dockerfile_path} -t {image_name} ."
        
        progress_manager.update_stage(container_name, 'build')
        build_code = run_command(build_cmd, build_log, f"{container_name}:build", verbose)
        
        if build_code != 0:
            debug_cmd = f"docker run {'--rm' if not keepfailed else ''} -it --entrypoint /bin/bash {image_name}"
            with status_lock:
                status[container_name] = {
                    'status': 'build_failed',
                    'code': build_code,
                    'log': build_log,
                    'image_name': image_name,
                    'debug_command': debug_cmd
                }
            print_manager.print(f"\nDocker build failed for {container_name}. Check logs at {build_log}")
            print_manager.print(f"To debug the build environment, run: {debug_cmd}")
            # Mark remaining stages as complete even in case of failure
            for stage in ['run', 'test', 'cleanup']:
                progress_manager.update_stage(container_name, stage)
            return

        # Run container with docker-opts from project config
        progress_manager.update_stage(container_name, 'run')
        run_log = os.path.join(log_dir, f'run_{timestamp}.log')
        docker_opts = project_info.get('docker-opts', '')
        run_cmd = f"docker run {docker_opts} --name {container_name} --replace {image_name}"
        
        progress_manager.update_stage(container_name, 'test')
        exit_code = run_command(run_cmd, run_log, f"{container_name}:run", verbose)
        
        debug_cmd = f"docker run {'--rm' if not keepfailed else ''} -it --entrypoint /bin/bash {docker_opts} {image_name}"
        with status_lock:
            status[container_name] = {
                'status': 'success' if exit_code == 0 else 'run_failed',
                'code': exit_code,
                'build_log': build_log,
                'run_log': run_log,
                'image_name': image_name,
                'debug_command': debug_cmd
            }
        
        if exit_code != 0:
            message = f"\nContainer {container_name} failed. Check logs at {run_log}"
            message += f"\nTo debug the container, run: {debug_cmd}"
        else:
            message = f"\nContainer {container_name} succeeded. Logs at {run_log}"
        print_manager.print(message)
        
        # Launch debug shell if test failed and debug mode is enabled
        if exit_code != 0 and debug:
            print_manager.print(f"\nLaunching debug shell in container {container_name}...")
            subprocess.run(debug_cmd, shell=True)
        
        # Cleanup based on success and keepfailed flag
        progress_manager.update_stage(container_name, 'cleanup')
        cleanup_log = os.path.join(log_dir, f'cleanup_{timestamp}.log')
        if exit_code == 0 or not keepfailed:
            run_command(f"docker rm {container_name}", cleanup_log)
    
    except Exception as e:
        debug_cmd = f"docker run {'--rm' if not keepfailed else ''} -it --entrypoint /bin/bash {docker_opts} {image_name}"
        print_manager.print(f"\nError processing container {container_name}: {str(e)}")
        print_manager.print(f"To debug the container, run: {debug_cmd}")
        # Mark remaining stages as complete in case of error
        for stage in ProgressManager.STAGES:
            progress_manager.update_stage(container_name, stage)
        with status_lock:
            status[container_name] = {
                'status': 'error',
                'error': str(e),
                'image_name': image_name,
                'debug_command': debug_cmd
            }
        raise

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
    """Sanitize tag name to be compatible with Docker/Podman"""
    # Convert tag to string if it's a number
    tag = str(tag)
    return tag.replace('/', '-').replace(':', '-')

def platform_worker(platform, config, status, status_lock, print_manager, progress_manager, debug=False, verbose=False, keepfailed=False):
    """Worker function to handle all containers for a single platform"""
    cmake_versions = config['cmake']['versions'] if 'cmake' in platform.get('depends', []) else [None]
    
    for cmake_version in cmake_versions:
        version_suffix = f"-cmake-{cmake_version}" if cmake_version else ""
        platform_tag = sanitize_tag(platform['version'] if platform['version'] != 'latest' else platform['image'])
        
        dockerfile_path = f"build/Dockerfile.{platform['name'].lower().replace(' ', '-')}{version_suffix}"
        image_name = f"{config['project']['name'].lower().replace(' ', '-')}:{platform_tag}{version_suffix}"
        container_name = f"{config['project']['name'].lower().replace(' ', '-')}-{platform['name'].lower().replace(' ', '-')}{version_suffix}"
        
        # Write Dockerfile
        progress_manager.update_stage(container_name, 'dockerfile')
        dockerfile_content = create_dockerfile(platform, config['cmake'], 
                                            config['project'], config['qemu'],
                                            config['python'], cmake_version)
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        
        # Process this platform's container
        docker_worker(dockerfile_path, image_name, container_name, 
                     status, status_lock, print_manager, config['project'],
                     progress_manager, debug, verbose, keepfailed)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Build and test in Docker containers')
    parser.add_argument('--debug', action='store_true', help='Launch a shell in the container if tests fail')
    parser.add_argument('--verbose', action='store_true', help='Print build and run output in real-time')
    parser.add_argument('--threading-level', choices=['platform', 'docker'], default='platform',
                       help='Control threading level: "platform" (one thread per platform) or "docker" (one thread per docker operation)')
    parser.add_argument('--keepfailed', action='store_true', help='Keep failed containers for debugging (default: remove all containers)')
    args = parser.parse_args()

    status = {}
    status_lock = Lock()
    print_manager = PrintManager()
    threads = []
    config = read_yaml_config('aocl-utils.yaml')
    
    # Calculate total number of containers
    total_containers = sum(
        len(config['cmake']['versions'] if 'cmake' in platform.get('depends', []) else [None])
        for platform in config['platforms']
        if can_build_platform(platform)
    )
    
    # Initialize progress manager and connect it to print manager
    progress_manager = ProgressManager(total_containers)
    print_manager.set_progress_manager(progress_manager)
    
    # Create necessary directories
    for dir in ['build', 'logs']:
        os.makedirs(dir, exist_ok=True)
    
    try:
        if args.threading_level == 'platform':
            # Platform-level threading
            for platform in config['platforms']:
                if not can_build_platform(platform):
                    print_manager.print(f"\nSkipping {platform['name']}: Required configuration not available")
                    continue
                    
                thread = Thread(target=platform_worker,
                              args=(platform, config, status, status_lock, print_manager, 
                                   progress_manager, args.debug, args.verbose, args.keepfailed))
                threads.append(thread)
                thread.start()
        else:
            # Docker-level threading
            for platform in config['platforms']:
                if not can_build_platform(platform):
                    print_manager.print(f"\nSkipping {platform['name']}: Required configuration not available")
                    continue
                
                cmake_versions = config['cmake']['versions'] if 'cmake' in platform.get('depends', []) else [None]
                for cmake_version in cmake_versions:
                    dockerfile_content = create_dockerfile(platform, config['cmake'], 
                                                        config['project'], config['qemu'],
                                                        cmake_version)
                    
                    version_suffix = f"-cmake-{cmake_version}" if cmake_version else ""
                    platform_tag = sanitize_tag(platform['version'] if platform['version'] != 'latest' else platform['image'])
                    
                    dockerfile_path = f"build/Dockerfile.{platform['name'].lower().replace(' ', '-')}{version_suffix}"
                    image_name = f"{config['project']['name'].lower().replace(' ', '-')}:{platform_tag}{version_suffix}"
                    container_name = f"{config['project']['name'].lower().replace(' ', '-')}-{platform['name'].lower().replace(' ', '-')}{version_suffix}"
                    
                    # Write Dockerfile
                    with open(dockerfile_path, 'w') as f:
                        f.write(dockerfile_content)
                    
                    # Create a thread for each docker operation
                    thread = Thread(target=docker_worker,
                                  args=(dockerfile_path, image_name, container_name, 
                                       status, status_lock, print_manager, config['project'],
                                       progress_manager, args.debug, args.verbose, args.keepfailed))
                    threads.append(thread)
                    thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
    finally:
        # Close progress bar
        progress_manager.close()
        
        # Print results
        print_manager.separator()
        print_manager.print("\nResults:")
        print_manager.pprint(status)
        
        # Write failed containers information
        write_failed_containers(status, print_manager)
        
        # Print logs for failures
        print_failure_logs(status, print_manager)
        
        # Determine overall status
        failed = any(result['status'] != 'success' for result in status.values())
        print_manager.print("\nOverall status: " + ("Failed" if failed else "Success"))
        print_manager.print(f"Failed containers: {failed}")
        print_manager.print(f"Please see failed_containers.txt for more information")
        
        # Stop the print manager
        print_manager.stop()

if __name__ == "__main__":
    main()
