"""
Script to create all __init__.py files for proper Python packaging.
Run this once to set up the module structure.
"""

import os
from pathlib import Path

# Directories that need __init__.py
INIT_DIRS = [
    "src",
    "src/models",
    "src/config", 
    "src/agents",
    "src/agents/infrastructure_discovery",
    "src/agents/infrastructure_discovery/cloud_adapters",
    "src/database",
    "src/api",
    "tests",
    "tests/agents",
]

INIT_CONTENT = '''"""Module initialization."""
'''

for dir_path in INIT_DIRS:
    init_file = Path(dir_path) / "__init__.py"
    init_file.parent.mkdir(parents=True, exist_ok=True)
    if not init_file.exists():
        init_file.write_text(INIT_CONTENT)
        print(f"Created {init_file}")
    else:
        print(f"Skipped {init_file} (exists)")

print("All __init__.py files created!")
