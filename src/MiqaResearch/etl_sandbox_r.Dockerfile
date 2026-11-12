# ETL sandbox R image (#166): the R runtime an R Script (script.R) executes inside. Layered on the
# Python sandbox image (etl_sandbox.Dockerfile) because the R shim is two halves (see
# mires_etl/r_shim.py): the platform's Python entrypoint launches `Rscript shim.R`
# for the Script itself, then validates the emitted rows against the ETL Datatype registry --
# so the Datatype schemas keep one source of truth instead of being re-expressed in R. Same
# isolation as the Python image: non-root, network-less, /sandbox staged via the archive API.
#
# Allowlist key: r-etl-v1 (language + runtime + release, #147) -- R from Debian bookworm
# (r-base-core 4.2) plus the curated set (#413): jsonlite (the shim), dplyr, readr, tidyr, lubridate.
# Replaces r-etl-v1 in place; a change to the list means a new key. The installed versions are
# appended to /etc/mires/packages.txt so each Job records them.
#
# Build (the Python image first -- this one builds FROM it):
#   docker compose --profile etl-sandbox-build build mires_etl_sandbox_python mires_etl_sandbox_r
# In production, pass BASE_IMAGE as the Python image's pinned digest reference.
ARG BASE_IMAGE=mires-etl-sandbox-python:dev
FROM ${BASE_IMAGE}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends r-base-core r-cran-jsonlite r-cran-dplyr r-cran-readr r-cran-tidyr r-cran-lubridate \
    && dpkg-query -W -f='${Package}==${Version}\n' r-base-core 'r-cran-*' >> /etc/mires/packages.txt \
    && rm -rf /var/lib/apt/lists/*
USER 65534:65534

ENV MIRES_ETL_SHIM_LANGUAGE=r
