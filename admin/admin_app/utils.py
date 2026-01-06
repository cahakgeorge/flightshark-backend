"""
Utility functions for Django Admin
"""
import os


def environment_callback(request):
    """
    Returns environment badge for Unfold admin
    """
    debug = os.environ.get('DEBUG', 'true').lower() == 'true'
    
    if debug:
        return ["Development", "warning"]
    else:
        return ["Production", "danger"]

