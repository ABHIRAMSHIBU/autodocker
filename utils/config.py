import yaml

class AutoDockerConfig:
    """
    Manages configuration for AutoDocker builds.
    
    This class handles loading and validating the YAML configuration,
    and provides easy access to configuration values.
    """
    def __init__(self, config_file):
        """
        Initialize configuration from YAML file.
        
        Args:
            config_file (str): Path to YAML configuration file
        
        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If config file is invalid YAML
        """
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self):
        """Load and validate configuration file."""
        try:
            with open(self.config_file, 'r') as f:
                config = yaml.safe_load(f)
                
            # Validate required sections
            required_sections = ['platforms', 'project']
            missing = [s for s in required_sections if s not in config]
            if missing:
                raise ValueError(f"Missing required sections in config: {', '.join(missing)}")
                
            return config
            
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file '{self.config_file}' not found")
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Error parsing YAML file: {e}")
    
    @property
    def platforms(self):
        """Get list of platform configurations."""
        return self.config['platforms']
    
    @property
    def project(self):
        """Get project configuration."""
        return self.config['project']
    
    @property
    def cmake_info(self):
        """Get CMake configuration."""
        return self.config.get('cmake')
    
    @property
    def cmake_versions(self):
        """Get list of CMake versions to build against."""
        if self.cmake_info:
            return self.cmake_info.get('versions', [])
        return []
    
    @property
    def qemu_info(self):
        """Get QEMU configuration."""
        return self.config.get('qemu')
    
    @property
    def python_info(self):
        """Get Python configuration."""
        return self.config.get('python')
    
    @property
    def ssh_config(self):
        """Get SSH configuration."""
        return self.config.get('ssh-keys')
    
    def get_dependencies(self):
        """Get all dependency configurations."""
        return {
            'python': self.python_info,
            'qemu': self.qemu_info,
            'aocl-utils': self.config.get('aocl-utils')
        }
    
    def get_platform_cmake_versions(self, platform):
        """
        Get CMake versions for a specific platform.
        
        Args:
            platform (dict): Platform configuration
        
        Returns:
            list: List of CMake versions or [None] if CMake not required
        """
        return self.cmake_versions if 'cmake' in platform.get('depends', []) else [None] 