"""Run gcloud with refreshed ADC in process memory if its separate login expired.

Tokens are passed only through the child environment, never argv or disk.
Usage: uv run python scripts/gcloud_adc.py run services list --project=...
"""
import os
import subprocess
import sys

import google.auth
from google.auth.transport.requests import Request

credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
credentials.refresh(Request())
env = os.environ.copy()
env["CLOUDSDK_AUTH_ACCESS_TOKEN"] = credentials.token
raise SystemExit(subprocess.call(["gcloud", *sys.argv[1:]], env=env))
