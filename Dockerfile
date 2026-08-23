# Errata -- the reviewer console, containerised for Cloud Run.
#
# This exists because Render's 512Mi ceiling killed the service on boot. `load_etim` holds every
# ETIM feature and value description in memory, and it deliberately loads ALL 5,640 classes --
# the docstring is explicit that a retriever which can only see the classes it was told about
# "would report perfect accuracy by construction". So the memory is not waste to be trimmed; it
# is what the honesty property costs. The fix is an instance that can hold it, not a smaller
# model.
#
# Deploy with scripts/deploy_gcp.sh, which sets --memory 2Gi and --min-instances 1.

FROM python:3.14-slim

# PyMuPDF ships manylinux wheels, so there is no compiler here on purpose: adding build-essential
# would triple the image for a dependency that does not need it. If a future dependency does need
# to build from source, add it in its own layer with the reason written down.
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The lockfile alone first, so the dependency layer is cached and a source edit does not reinstall
# 26 packages. requirements-lock.txt was frozen on Python 3.14.3, which is why the base image is
# 3.14 rather than the 3.11 that pyproject names as a lint target.
COPY requirements-lock.txt ./
RUN python -m pip install --upgrade pip setuptools wheel \
 && python -m pip install -r requirements-lock.txt

COPY . .

# --no-deps: every intra-repo dependency is satisfied by this same command, and resolving them
# would reach PyPI for distributions that only exist here. All EIGHT of them -- bundle owns the
# page projection and errata_audit.console imports it.
RUN python -m pip install --no-deps \
      -e ./valuesem -e ./spec -e ./comparator -e ./bench \
      -e ./audit -e ./scale -e ./ecosystem -e ./bundle

# Reference data is baked into the image rather than fetched at boot. Two reasons: a cold start
# that downloads 22MB from three third-party hosts is a cold start that can fail for reasons
# nobody controls, and an image whose contents are fixed is one whose sha256 means something.
# Every file is hash-verified against data/reference/manifest.json as it lands.
RUN python scripts/fetch_deploy_data.py

# Cloud Run injects PORT and it is not negotiable. --allow-remote is required because the CLI
# refuses a non-loopback bind without it: the console has NO AUTHENTICATION, and that flag is
# where the operator says so out loud rather than a default saying it for them.
ENV PORT=8080
EXPOSE 8080

# Shell form, deliberately: $PORT has to expand at runtime, and exec form would pass it literally.
CMD errata-audit serve --host 0.0.0.0 --port $PORT --allow-remote
