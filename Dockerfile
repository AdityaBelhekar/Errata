# Errata -- the reviewer console, containerised.
#
# Targets Hugging Face Spaces (Docker SDK) and works unchanged on Cloud Run.
#
# WHY A CONTAINER AT ALL
#
# Render's 512Mi ceiling OOM-killed the service on boot. The memory is not waste to be trimmed:
# `load_etim` holds every ETIM feature and value description, and it loads all 5,640 classes on
# purpose -- the docstring is explicit that a retriever which can only see the classes it was
# told about "would report perfect accuracy by construction". Shrinking the model to fit the
# instance would have deleted the property that makes its accuracy number mean anything. The fix
# is a host that can hold it: HF Spaces' free CPU tier gives 16GB.
#
# TWO THINGS THIS FILE IS CAREFUL ABOUT
#
# 1. It runs as UID 1000, not root. HF Spaces runs containers as a non-root user, and the console
#    WRITES at runtime -- `var/audit/ledger.jsonl` is an append-only decision log, opened on the
#    first adjudication rather than at boot. Left as root-owned, the Space would start, serve the
#    queue, and fail the moment a reviewer actually decided something: the worst possible time to
#    discover a permission bug.
#
# 2. PORT defaults to 7860, which is what HF expects and what `app_port` in README.md declares.
#    Cloud Run injects its own PORT and overrides this, so the same image serves both.

FROM python:3.14-slim

# PyMuPDF ships manylinux wheels, so no compiler is installed on purpose: build-essential would
# triple the image for a dependency that does not need it.

# HF Spaces convention: a real user with a home directory, everything owned by it.
RUN useradd --create-home --uid 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR $HOME/app

# The lockfile alone first, so the dependency layer caches and a source edit does not reinstall
# 26 packages. requirements-lock.txt was frozen on Python 3.14.3 -- hence the 3.14 base image
# rather than the 3.11 that pyproject names as a ruff/mypy target.
COPY --chown=user requirements-lock.txt ./
RUN python -m pip install --user --upgrade pip setuptools wheel \
 && python -m pip install --user -r requirements-lock.txt

COPY --chown=user . .

# --no-deps: every intra-repo dependency is satisfied by this same command, and resolving them
# would reach PyPI for distributions that only exist here. All EIGHT -- bundle owns the page
# projection and errata_audit.console imports it, which is what broke the first Render build.
RUN python -m pip install --user --no-deps \
      -e ./valuesem -e ./spec -e ./comparator -e ./bench \
      -e ./audit -e ./scale -e ./ecosystem -e ./bundle

# Reference data is baked in rather than fetched at boot: a cold start that downloads 22MB from
# three third-party hosts is a cold start that fails for reasons nobody controls. Two of the
# manifest's ten publishers already answer 403. Every file is hash-verified as it lands.
RUN python scripts/fetch_deploy_data.py

# The append-only decision ledger. Created here so the directory exists and is owned correctly
# before any reviewer touches it, rather than on first write.
RUN mkdir -p var/audit

ENV PORT=7860
EXPOSE 7860

# Shell form, deliberately: $PORT has to expand at runtime. --allow-remote is required because
# the CLI refuses a non-loopback bind without it -- the console has NO AUTHENTICATION, and that
# flag is where an operator says so out loud instead of a default saying it for them.
CMD errata-audit serve --host 0.0.0.0 --port $PORT --allow-remote
