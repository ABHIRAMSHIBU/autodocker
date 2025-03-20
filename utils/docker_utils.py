def sanitize_tag(tag):
    """
    Sanitize tag name to be compatible with Docker/Podman.
    
    Args:
        tag (str|int): Tag to sanitize
    
    Returns:
        str: Sanitized tag string
    """
    # Convert tag to string if it's a number
    tag = str(tag)
    return tag.replace('/', '-').replace(':', '-')

def sanitize_name(name):
    """
    Sanitize a name for use in Docker tags and container names.
    
    Args:
        name (str): Name to sanitize
        
    Returns:
        str: Sanitized name
    """
    return name.lower().replace(' ', '-')

def get_container_name(platform, cmake_version):
    """
    Generate a container name from platform and CMake version.
    
    Args:
        platform (dict): Platform configuration
        cmake_version (str): CMake version or None
        
    Returns:
        str: Container name
    """
    base_name = sanitize_name(platform['name'])
    version_suffix = f"-cmake-{cmake_version}" if cmake_version else ""
    return f"{base_name}{version_suffix}"

def get_image_name(platform, cmake_version):
    """
    Generate an image name from platform and CMake version.
    
    Args:
        platform (dict): Platform configuration
        cmake_version (str): CMake version or None
        
    Returns:
        str: Image name
    """
    platform_tag = sanitize_name(platform['version'] if platform['version'] != 'latest' else platform['image'])
    version_suffix = f"-cmake-{cmake_version}" if cmake_version else ""
    return f"{platform_tag}{version_suffix}"

def get_image_name_from_container(container_name):
    """
    Extract image name from container name.
    
    Args:
        container_name (str): Container name
        
    Returns:
        str: Image name
    """
    parts = container_name.split('-')
    if 'cmake' in parts:
        cmake_idx = parts.index('cmake')
        return '-'.join(parts[:cmake_idx] + parts[cmake_idx:])
    return container_name 