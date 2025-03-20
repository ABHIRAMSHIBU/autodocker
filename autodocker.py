import os
import sys
import argparse
from threading import Thread, Lock

from managers.print_manager import PrintManager
from managers.progress_manager import ProgressManager
from managers.log_manager import LogManager
from managers.docker_manager import DockerManager
from managers.container_manager import ContainerManager

from utils.config import AutoDockerConfig
from utils.docker_utils import get_container_name, get_image_name
from utils.platform_utils import can_build_platform

from dockerfile.generator import create_dockerfile

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
            
            # Print failure logs and write failed containers information
            self.log_manager.print_failure_logs(self.status, self.print_manager)
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
