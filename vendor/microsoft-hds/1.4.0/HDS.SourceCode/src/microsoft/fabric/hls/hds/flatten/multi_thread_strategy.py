# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# --------------------------------------------------------------------------
"""
The module for multithread strategy enumeration
"""
from enum import Enum

# define enum for flattenManager multithread strategy
class MultithreadStrategy(Enum):
    """
    Enum for multithread strategy
    
    Values:
        -  ONE_THREAD_PER_RESOURCE (1): use one thread per resource, 
        so we will create a thread with number of workers for each resource
        -  SPECIFIED_IN_CONFIG (2): use one number of threads specified in config
    """
    # use one thread per resource
    ONE_THREAD_PER_RESOURCE = 1
    # use one thread per column
    SPECIFIED_IN_CONFIG = 2