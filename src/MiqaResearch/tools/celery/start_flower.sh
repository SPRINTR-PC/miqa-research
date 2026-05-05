#!/bin/bash

set -o errexit
set -o nounset

if [[ -n "${SET_CELERY_PYTHON_PATH:-}" ]]; then
  PYTHONPATH=$(dirname "$0")/../.. celery -A MiqaResearch flower 
else
  celery -A MiqaResearch flower
fi
