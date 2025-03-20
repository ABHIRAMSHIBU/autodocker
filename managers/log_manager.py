import os
from datetime import datetime
from utils.docker_utils import get_image_name_from_container

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
    
    def print_failure_logs(self, status, print_manager):
        """
        Print logs for failed builds/runs.
        
        Args:
            status (dict): Status dictionary
            print_manager (PrintManager): Print manager for output
        """
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