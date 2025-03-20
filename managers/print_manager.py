from pprint import pprint

class PrintManager:
    """
    Manages console output with optional progress bar integration.
    """
    def __init__(self, progress_manager=None):
        """
        Initialize print manager.
        
        Args:
            progress_manager (ProgressManager): Progress manager for tracking
        """
        self.progress_manager = progress_manager
        
    def set_progress_manager(self, progress_manager):
        """
        Set progress manager.
        
        Args:
            progress_manager (ProgressManager): Progress manager for tracking
        """
        self.progress_manager = progress_manager
    
    def print(self, message):
        """
        Print a message, handling progress bar if present.
        
        Args:
            message (str): Message to print
        """
        if self.progress_manager:
            self.progress_manager.clear()
        print(message)
        if self.progress_manager:
            self.progress_manager.refresh()
    
    def pprint(self, obj):
        """
        Pretty print an object.
        
        Args:
            obj: Object to print
        """
        if self.progress_manager:
            self.progress_manager.clear()
        pprint(obj)
        if self.progress_manager:
            self.progress_manager.refresh()
    
    def print_file(self, file_path):
        """
        Print contents of a file.
        
        Args:
            file_path (str): Path to file
        """
        try:
            with open(file_path, 'r') as f:
                if self.progress_manager:
                    self.progress_manager.clear()
                print(f.read())
                if self.progress_manager:
                    self.progress_manager.refresh()
        except Exception as e:
            self.print(f"Error reading file {file_path}: {str(e)}")
    
    def separator(self, char='-', length=80):
        """
        Print a separator line.
        
        Args:
            char (str): Character to use for separator
            length (int): Length of separator
        """
        self.print(char * length)
    
    def stop(self):
        """Stop the progress manager if it exists."""
        if self.progress_manager:
            self.progress_manager.close() 