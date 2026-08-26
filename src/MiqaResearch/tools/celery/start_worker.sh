#!/bin/bash

set -o errexit
set -o nounset

CELERY_WORKER_OPTIONS=(
  -A MiqaResearch
  worker
  -l INFO
  -Q "${1}"
)

if [[ -n "${SET_CELERY_PYTHON_PATH:-}" ]]; then
  PYTHONPATH=$(dirname "$0")/../.. celery "${CELERY_WORKER_OPTIONS[@]}"
else
  celery "${CELERY_WORKER_OPTIONS[@]}"
fi
