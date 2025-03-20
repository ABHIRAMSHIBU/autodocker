import subprocess

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