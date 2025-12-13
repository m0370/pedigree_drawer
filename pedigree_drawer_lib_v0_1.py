"""
pedigree_drawer_lib_v0_1.py

Backward-compatibility shim for older instructions/imports.

v0.2 uses `pedigree_drawer_lib_v0_2.PedigreeChart` as the canonical renderer.
This module keeps `from pedigree_drawer_lib_v0_1 import PedigreeChart` working.
"""

from pedigree_drawer_lib_v0_2 import PedigreeChart  # noqa: F401

