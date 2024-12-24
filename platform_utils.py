try:
    from conf import RHEL_SUBSCRIPTION
except ImportError:
    RHEL_SUBSCRIPTION = None

def can_build_platform(platform):
    """Check if platform can be built with available configurations"""
    if 'redhat' in platform['image'].lower() and not RHEL_SUBSCRIPTION:
        return False
    return True

def process_requirements_cmd(platform):
    """Process and return modified requirements command based on platform"""
    cmd = platform['requirements-cmd']
    if 'redhat' in platform['image'].lower() and RHEL_SUBSCRIPTION:
        cmd = cmd.replace('<ORG>', RHEL_SUBSCRIPTION['org'])
        cmd = cmd.replace('<ACTIVATION_KEY>', RHEL_SUBSCRIPTION['activation_key'])
    return cmd
