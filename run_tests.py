# /// script
# requires-python = ">=3.12"
# dependencies = [
# "pytest>=8.0.0",
# "claude-saga==0.1.0"
# ]
# ///

"""Test runner for session_start.py saga tests"""

import sys

import pytest

if __name__ == "__main__":
    # Run pytest with the test file
    sys.exit(pytest.main(["-v", "tests/test_session_start.py"]))
