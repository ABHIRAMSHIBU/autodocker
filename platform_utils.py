try:
    from conf import RHEL_SUBSCRIPTION
except ImportError:
    RHEL_SUBSCRIPTION = None

def can_build_platform(platform):
    """
    Check if a platform can be built with available configurations.
    
    Args:
        platform (dict): Platform configuration dictionary containing at least:
            - image (str): Base image name (e.g., 'redhat', 'ubuntu')
    
    Returns:
        bool: True if platform can be built, False if missing required configurations
              (e.g., RHEL subscription for RedHat-based images)
    """
    if 'redhat' in platform['image'].lower() and not RHEL_SUBSCRIPTION:
        return False
    return True

def process_requirements_cmd(platform):
    """
    Process and return modified requirements command based on platform.
    Handles special cases like RHEL subscription replacement.
    
    Args:
        platform (dict): Platform configuration dictionary containing:
            - image (str): Base image name
            - requirements-cmd (str): Base requirements installation command
    
    Returns:
        str: Modified requirements command with replacements applied
             (e.g., RHEL subscription details inserted)
    """
    cmd = platform['requirements-cmd']
    if 'redhat' in platform['image'].lower() and RHEL_SUBSCRIPTION:
        cmd = cmd.replace('<ORG>', RHEL_SUBSCRIPTION['org'])
        cmd = cmd.replace('<ACTIVATION_KEY>', RHEL_SUBSCRIPTION['activation_key'])
    return cmd
