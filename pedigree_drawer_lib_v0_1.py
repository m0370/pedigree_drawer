"""
Compatibility shim.

The original v0.1 docs referenced `pedigree_drawer_lib_v0.1.py`, but a dot in a module
name cannot be imported in Python (e.g. `from foo_v0.1 import ...` is a syntax error).

Use this module instead:
    from pedigree_drawer_lib_v0_1 import PedigreeChart

Implementation lives in `pedigree_drawer_lib.py`.
"""

from pedigree_drawer_lib import PedigreeChart  # noqa: F401

