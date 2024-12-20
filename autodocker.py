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

def get_cmake_setup(platform, cmake_info):
    """Generate CMake installation if needed"""
    if 'cmake' not in platform.get('depends', []):
        return ""
    
    return f"""# Install CMake
WORKDIR /tmp
RUN wget {cmake_info['url'].replace('<version>', cmake_info['versions'][0])}
RUN bash cmake-{cmake_info['versions'][0]}-linux-x86_64.sh --skip-license --prefix=/usr/local
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

def create_dockerfile(platform, cmake_info, project_info, qemu_info):
    """Combine all Dockerfile sections"""
    sections = [
        get_base_setup(platform),
        get_cmake_setup(platform, cmake_info),
        get_qemu_setup(platform, qemu_info),
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
        dockerfile_content = create_dockerfile(platform, config['cmake'], 
                                            config['project'], config['qemu'])
        
        # Write Dockerfile
        dockerfile_path = f"build/Dockerfile.{platform['name'].lower().replace(' ', '-')}"
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        
        # Build Docker image using buildx
        image_tag = platform['version'] if platform['version'] != 'latest' else platform['image']
        image_name = f"{config['project']['name'].lower().replace(' ', '-')}:{image_tag}"
        os.system(f"docker buildx build -f {dockerfile_path} -t {image_name} .")

        # Run Docker container
        container_name = f"{config['project']['name'].lower().replace(' ', '-')}-{platform['name'].lower().replace(' ', '-')}"
        exit_code = os.system(f"docker run -it --name {container_name} --replace {image_name}")
        
        status[container_name] = exit_code
        if exit_code != 0:
            print(f"Container {container_name} exited with code {exit_code}")
        else:
            print(f"Container {container_name} ran successfully")
        
        # Clean up the container
        os.system(f"docker rm {container_name}")
    
    print("Results:")
    pprint(status)
    print("Overall status: ", "Failed" if any(status.values()) else "Success")
        
if __name__ == "__main__":
    main()
