import yaml
import os
from string import Template
from pprint import pprint
from threading import Thread, Lock
from queue import Queue
import time

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

def docker_worker(dockerfile_path, image_name, container_name, status, status_lock):
    """Worker function to handle Docker build and run operations"""
    # Build Docker image
    build_code = os.system(f"docker buildx build -f {dockerfile_path} -t {image_name} .")
    
    if build_code != 0:
        with status_lock:
            status[container_name] = build_code
        print(f"Docker build failed for {container_name} with code {build_code}")
        return

    # Run container
    exit_code = os.system(f"docker run -it --name {container_name} --replace {image_name}")
    
    with status_lock:
        status[container_name] = exit_code
    
    if exit_code != 0:
        print(f"Container {container_name} exited with code {exit_code}")
    else:
        print(f"Container {container_name} ran successfully")
    
    # Cleanup
    os.system(f"docker rm {container_name}")

def main():
    status = {}
    status_lock = Lock()
    threads = []
    config = read_yaml_config('aocl-utils.yaml')
    
    if not os.path.exists('build'):
        os.makedirs('build')
    
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
                          args=(dockerfile_path, image_name, container_name, status, status_lock))
            threads.append(thread)
            thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    print("\nResults:")
    pprint(status)
    print("Overall status: ", "Failed" if any(status.values()) else "Success")

if __name__ == "__main__":
    main()
