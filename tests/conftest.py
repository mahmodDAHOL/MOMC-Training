import os
import sys

# Pure modules are importable without Frappe; put the app package on the path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
