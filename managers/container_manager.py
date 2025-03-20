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