"""
tests/test_assettocorsa_provider.py (Redirect to ACC Provider Test)
==================================================================
No ACCTelemetry, os testes do provider são executados via test_acc_provider.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_acc_provider import *
