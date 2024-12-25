#!/usr/bin/env python3

import os
import re
import subprocess
import sys
import inquirer
from typing import Dict, List, Optional

class ContainerDebugger:
    def __init__(self):
        self.failed_containers: Dict[str, Dict[str, str]] = {}
        self.file_path = 'failed_containers.txt'

    def parse_failed_containers(self) -> bool:
        """Parse the failed_containers.txt file"""
        if not os.path.exists(self.file_path):
            print(f"Error: {self.file_path} not found.")
            print("Please run the container tests first to generate the file.")
            return False

        try:
            with open(self.file_path, 'r') as f:
                content = f.read()

            # Split content into container sections
            sections = content.split('-' * 50)
            
            for section in sections:
                if not section.strip():
                    continue
                
                # Extract container information using regex
                container_match = re.search(r'Container: (.+)', section)
                status_match = re.search(r'Status: (.+)', section)
                image_match = re.search(r'Image: (.+)', section)
                debug_cmd_match = re.search(r'Debug Command: (.+)', section)
                
                if container_match:
                    container_name = container_match.group(1).strip()
                    self.failed_containers[container_name] = {
                        'status': status_match.group(1).strip() if status_match else 'unknown',
                        'image': image_match.group(1).strip() if image_match else 'unknown',
                        'debug_command': debug_cmd_match.group(1).strip() if debug_cmd_match else ''
                    }
            
            return bool(self.failed_containers)
        
        except Exception as e:
            print(f"Error parsing {self.file_path}: {str(e)}")
            return False

    def show_menu(self) -> Optional[str]:
        """Show interactive menu to select a container"""
        if not self.failed_containers:
            return None

        # Prepare container choices with status
        choices = [
            f"{name} ({info['status']})"
            for name, info in self.failed_containers.items()
        ]

        questions = [
            inquirer.List('container',
                         message="Select a container to debug",
                         choices=choices,
                         carousel=True)
        ]

        try:
            answers = inquirer.prompt(questions)
            if answers:
                # Extract container name from the selection (remove status)
                selected = answers['container'].split(' (')[0]
                return selected
            return None
        except Exception as e:
            print(f"Error displaying menu: {str(e)}")
            return None

    def debug_container(self, container_name: str) -> None:
        """Debug the selected container"""
        if container_name not in self.failed_containers:
            print(f"Error: Container {container_name} not found in failed containers list")
            return

        container_info = self.failed_containers[container_name]
        debug_cmd = container_info['debug_command']

        if not debug_cmd:
            print(f"Error: No debug command available for {container_name}")
            return

        print(f"\nStarting debug session for {container_name}")
        print(f"Status: {container_info['status']}")
        print(f"Image: {container_info['image']}")
        print("\nExecuting debug command...")
        print(f"Command: {debug_cmd}\n")

        try:
            subprocess.run(debug_cmd, shell=True)
        except KeyboardInterrupt:
            print("\nDebug session terminated by user")
        except Exception as e:
            print(f"Error executing debug command: {str(e)}")

def main():
    debugger = ContainerDebugger()
    
    # Parse failed containers file
    if not debugger.parse_failed_containers():
        sys.exit(1)
    
    while True:
        # Show menu and get selection
        selected_container = debugger.show_menu()
        
        if selected_container is None:
            break
        
        # Debug selected container
        debugger.debug_container(selected_container)
        
        # Ask if user wants to debug another container
        questions = [
            inquirer.Confirm('continue',
                           message="Would you like to debug another container?",
                           default=True)
        ]
        
        try:
            answers = inquirer.prompt(questions)
            if not answers or not answers['continue']:
                break
        except Exception:
            break

    print("\nDebug session ended")

if __name__ == "__main__":
    main() 