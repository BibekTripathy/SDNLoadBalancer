#!/usr/bin/env python3
"""
Ryu Manager Launcher with Eventlet Compatibility Patch.

Provides a compatibility wrapper for Ryu 4.34 on modern Python 3.10+ environments.
Fixes:
1. Eventlet wsgi ALREADY_HANDLED missing constant attribute.
2. Ensures project root is in sys.path for direct custom controller imports.
"""

import os
import sys
import warnings

# Suppress Eventlet deprecation warnings in terminal logs
warnings.filterwarnings("ignore")

# Add project root directory to Python module search path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Apply Eventlet WSGI ALREADY_HANDLED compatibility patch before Ryu imports
import eventlet.wsgi

if not hasattr(eventlet.wsgi, "ALREADY_HANDLED"):
    eventlet.wsgi.ALREADY_HANDLED = True

from ryu.cmd.manager import main


if __name__ == "__main__":
    main()
