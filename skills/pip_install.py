import subprocess
import logging

def pip_install(package_name):
    """
    Safely installs a python package via pip and logs the activity.
    """
    try:
        # Run pip install
        result = subprocess.run(['pip', 'install', package_name], capture_output=True, text=True, check=True)
        message = f"Successfully installed {package_name}: {result.stdout}"
        print(message)
        return message
    except subprocess.CalledProcessError as e:
        error_msg = f"Failed to install {package_name}: {e.stderr}"
        print(error_msg)
        return error_msg
