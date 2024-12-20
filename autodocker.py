import yaml
import os
from pprint import pprint
from threading import Thread, Lock
import subprocess
from datetime import datetime
import sys
from queue import Queue, Empty

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
RUN {platform['requirements-cmd']}
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

def create_dockerfile(platform, cmake_info, project_info, qemu_info, cmake_version):
    """Combine all Dockerfile sections"""
    sections = [
        get_base_setup(platform),
        get_qemu_setup(platform, qemu_info),
        get_cmake_setup(platform, cmake_info, cmake_version),
        get_project_setup(project_info)
    ]
    return "\n".join(sections)

def run_command(cmd, logfile):
    """Run a command and log its output"""
    with open(logfile, 'w') as f:
        process = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        for line in process.stdout:
            f.write(line)
            f.flush()
        
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
        self.printer_thread = Thread(target=self._printer_worker)
        self.printer_thread.daemon = True
        self.printer_thread.start()

    def _printer_worker(self):
        while self.is_running or not self.print_queue.empty():
            try:
                message = self.print_queue.get(timeout=0.1)
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

def docker_worker(dockerfile_path, image_name, container_name, status, status_lock, print_manager):
    """Worker function to handle Docker build and run operations"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join('logs', container_name)
    os.makedirs(log_dir, exist_ok=True)
    
    # Build Docker image
    build_log = os.path.join(log_dir, f'build_{timestamp}.log')
    build_cmd = f"docker buildx build -f {dockerfile_path} -t {image_name} ."
    build_code = run_command(build_cmd, build_log)
    
    if build_code != 0:
        with status_lock:
            status[container_name] = {
                'status': 'build_failed',
                'code': build_code,
                'log': build_log
            }
        print_manager.print(f"\nDocker build failed for {container_name}. Check logs at {build_log}")
        return

    # Run container
    run_log = os.path.join(log_dir, f'run_{timestamp}.log')
    run_cmd = f"docker run -it --name {container_name} --replace {image_name}"
    exit_code = run_command(run_cmd, run_log)
    
    with status_lock:
        status[container_name] = {
            'status': 'success' if exit_code == 0 else 'run_failed',
            'code': exit_code,
            'build_log': build_log,
            'run_log': run_log
        }
    
    message = (f"\nContainer {container_name} failed. Check logs at {run_log}" 
              if exit_code != 0 else 
              f"\nContainer {container_name} succeeded. Logs at {run_log}")
    print_manager.print(message)
    
    # Cleanup
    cleanup_log = os.path.join(log_dir, f'cleanup_{timestamp}.log')
    run_command(f"docker rm {container_name}", cleanup_log)

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

def main():
    status = {}
    status_lock = Lock()
    print_manager = PrintManager()
    threads = []
    config = read_yaml_config('aocl-utils.yaml')
    
    # Create necessary directories
    for dir in ['build', 'logs']:
        os.makedirs(dir, exist_ok=True)
    
    for platform in config['platforms']:
        cmake_versions = config['cmake']['versions'] if 'cmake' in platform.get('depends', []) else [None]
        
        for cmake_version in cmake_versions:
            dockerfile_content = create_dockerfile(platform, config['cmake'], 
                                                config['project'], config['qemu'],
                                                cmake_version)
            
            version_suffix = f"-cmake-{cmake_version}" if cmake_version else ""
            platform_tag = platform['version'] if platform['version'] != 'latest' else platform['image']
            
            dockerfile_path = f"build/Dockerfile.{platform['name'].lower().replace(' ', '-')}{version_suffix}"
            image_name = f"{config['project']['name'].lower().replace(' ', '-')}:{platform_tag}{version_suffix}"
            container_name = f"{config['project']['name'].lower().replace(' ', '-')}-{platform['name'].lower().replace(' ', '-')}{version_suffix}"
            
            # Write Dockerfile
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            
            # Create and start worker thread
            thread = Thread(target=docker_worker, 
                          args=(dockerfile_path, image_name, container_name, 
                                status, status_lock, print_manager))
            threads.append(thread)
            thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Print results
    print_manager.separator()
    print_manager.print("\nResults:")
    print_manager.pprint(status)
    
    # Print logs for failures
    print_failure_logs(status, print_manager)
    
    # Determine overall status
    failed = any(result['status'] != 'success' for result in status.values())
    print_manager.print("\nOverall status: " + ("Failed" if failed else "Success"))
    
    # Stop the print manager
    print_manager.stop()

if __name__ == "__main__":
    main()
