import yaml
import os
from string import Template
from pprint import pprint

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

def main():
    status = {}
    config = read_yaml_config('aocl-utils.yaml')
    
    # Create build directory if it doesn't exist
    if not os.path.exists('build'):
        os.makedirs('build')
    
    # Generate Dockerfile for each platform
    for platform in config['platforms']:
        # Iterate over CMake versions if platform depends on CMake
        cmake_versions = config['cmake']['versions'] if 'cmake' in platform.get('depends', []) else [None]
        
        for cmake_version in cmake_versions:
            # Generate Dockerfile
            dockerfile_content = create_dockerfile(platform, config['cmake'], 
                                                config['project'], config['qemu'],
                                                cmake_version)
            
            # Create platform-specific + cmake-version-specific names
            version_suffix = f"-cmake-{cmake_version}" if cmake_version else ""
            platform_tag = platform['version'] if platform['version'] != 'latest' else platform['image']
            
            dockerfile_path = f"build/Dockerfile.{platform['name'].lower().replace(' ', '-')}{version_suffix}"
            image_name = f"{config['project']['name'].lower().replace(' ', '-')}:{platform_tag}{version_suffix}"
            container_name = f"{config['project']['name'].lower().replace(' ', '-')}-{platform['name'].lower().replace(' ', '-')}{version_suffix}"
            
            # Write Dockerfile and build image
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            
            os.system(f"docker buildx build -f {dockerfile_path} -t {image_name} .")
            
            # Run and cleanup container
            exit_code = os.system(f"docker run -it --name {container_name} --replace {image_name}")
            status[container_name] = exit_code
            
            if exit_code != 0:
                print(f"Container {container_name} exited with code {exit_code}")
            else:
                print(f"Container {container_name} ran successfully")
            
            os.system(f"docker rm {container_name}")
    
    print("Results:")
    pprint(status)
    print("Overall status: ", "Failed" if any(status.values()) else "Success")
        
if __name__ == "__main__":
    main()
