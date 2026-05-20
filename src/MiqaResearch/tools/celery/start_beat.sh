#!/bin/bash

set -o errexit
set -o nounset

rm -f './celerybeat.pid'

if [[ -n "${SET_CELERY_PYTHON_PATH:-}" ]]; then
  PYTHONPATH=$(dirname "$0")/../.. celery -A MiqaResearch beat -l INFO
else
  celery -A MiqaResearch beat -l INFO
fi
