def can_build_platform(platform):
    """
    Check if a platform can be built on the current system.
    
    Args:
        platform (dict): Platform configuration
        
    Returns:
        bool: True if platform can be built, False otherwise
    """
    # For now, we assume all platforms can be built
    # In the future, we can add checks for required tools, etc.
    return True

def process_requirements_cmd(platform):
    """
    Process the requirements command for a platform.
    
    Args:
        platform (dict): Platform configuration
        
    Returns:
        str: Processed requirements command
    """
    # For now, we just return the command as is
    # In the future, we can add processing logic
    return platform['requirements-cmd'] 