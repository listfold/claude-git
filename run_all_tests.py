# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pytest>=8.0.0",
# "claude-saga==0.1.0"
# ]
# ///

"""Test runner for all saga tests"""

import sys

import pytest

if __name__ == "__main__":
    # Run pytest with all test files
    sys.exit(pytest.main(["-v", "tests/"]))
