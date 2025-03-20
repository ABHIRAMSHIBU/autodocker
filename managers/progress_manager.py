from threading import Lock
from tqdm import tqdm

class ProgressManager:
    """
    Manages progress bar for tracking container builds.
    """
    def __init__(self, total):
        """
        Initialize progress manager.
        
        Args:
            total (int): Total number of containers to build
        """
        self.progress = tqdm(total=total, desc="Building containers", unit="container")
        self.stages = {}
        self.stage_lock = Lock()
    
    def update_stage(self, container, stage):
        """
        Update stage for a container.
        
        Args:
            container (str): Container name
            stage (str): Current stage
        """
        with self.stage_lock:
            self.stages[container] = stage
            desc = f"Building containers ({', '.join(f'{k}: {v}' for k, v in self.stages.items())})"
            self.progress.set_description(desc)
    
    def increment(self):
        """Increment progress counter."""
        self.progress.update(1)
    
    def clear(self):
        """Clear progress bar."""
        self.progress.clear()
    
    def refresh(self):
        """Refresh progress bar."""
        self.progress.refresh()
    
    def close(self):
        """Close progress bar."""
        self.progress.close() 