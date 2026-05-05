#!/bin/bash

set -o errexit
set -o nounset

if [[ -n "${SET_CELERY_PYTHON_PATH:-}" ]]; then
  PYTHONPATH=$(dirname "$0")/../.. celery -A MiqaResearch worker -l INFO -Q st1_cpu
else
  celery -A MiqaResearch worker -l INFO -Q st1_cpu
fi
