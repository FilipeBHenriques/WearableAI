"""Test package init — disable service logging for all test runs."""

import os

os.environ["SERVICE_LOG_ENABLED"] = "0"
