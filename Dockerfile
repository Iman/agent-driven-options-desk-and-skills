# Option desk: the CLI and the local dashboard, pinned.
#
# WHAT THIS IMAGE IS FOR. Running the tools without installing Python, and
# getting the same interpreter and the same optional dependencies every
# time. It is the right choice on a machine with no Python, on Windows, and
# in CI.
#
# WHAT IT CANNOT DO, and this is most of the project. The six skills are
# markdown that has to sit in ~/.claude/skills or ~/.agents/skills on the
# HOST, because the host's agent is what reads them. The MCP server is a
# stdio process that an agent runtime launches itself. Neither reaches an
# agent running outside this container. For those, use ./install.sh or the
# plugin marketplaces; see INSTALL.md.
#
# ARTIFACTS ARE THE PRODUCT. Every command writes a schema-validated JSON
# file, and a container that is not given a volume writes them into itself
# and loses them on exit while reporting success. That is the one failure
# this project refuses to ship, so the entrypoint checks for a mount and
# says so rather than working silently and throwing the results away.

FROM python:3.13-slim AS base

# Nothing is compiled here: the engine is standard library only and the
# optional dependencies ship wheels. No build toolchain in the image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OPTIONDESK_ARTIFACTS=/artifacts \
    PIP_NO_CACHE_DIR=1

WORKDIR /src

# Copy the three packages first so a documentation change does not
# invalidate the dependency layer.
COPY shell/pyproject.toml shell/
COPY engine/pyproject.toml engine/
COPY agent/pyproject.toml agent/
COPY shell/src shell/src
COPY engine/src engine/src
COPY agent/src agent/src

RUN python -m pip install --upgrade pip \
 && python -m pip install "./shell[yahoo,dashboard]" ./engine

# The skills, the disclaimer and the licence travel with the image so that
# anyone who exec's into it can read what they are running and under what
# terms.
COPY shell/skills /opt/option-desk/skills
COPY DISCLAIMER.md LICENSE LICENSES.md THIRD-PARTY.md /opt/option-desk/

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Not root. The tool reaches the network for market data and writes files;
# neither needs privileges.
RUN useradd --create-home --uid 10001 desk \
 && mkdir -p /artifacts \
 && chown -R desk:desk /artifacts
USER desk

# No VOLUME instruction, deliberately, and this was measured rather than
# reasoned about. Declaring it makes Docker create an ANONYMOUS volume and
# mount it at run time, so `mountpoint /artifacts` is always true and the
# entrypoint's check for a real mount can never fire. With --rm that
# anonymous volume is then discarded, which is the exact data loss the
# check exists to prevent, made invisible by the instruction meant to
# advertise it. Without VOLUME, /artifacts is an ordinary directory unless
# the user mounts over it, and the check works.
EXPOSE 8787

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["doctor"]

LABEL org.opencontainers.image.title="option desk" \
      org.opencontainers.image.description="Options analytics an AI agent can drive and a person can read. CLI and local dashboard. Research software, not investment advice." \
      org.opencontainers.image.licenses="PolyForm-Noncommercial-1.0.0" \
      org.opencontainers.image.source="https://github.com/Iman/agent-driven-options-desk-and-skills"
