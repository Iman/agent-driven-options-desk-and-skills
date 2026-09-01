#!/bin/sh
# Refuse to lose somebody's work quietly.
#
# Artifacts are the product of every command here, and a container run
# without a volume writes them inside itself and discards them on exit,
# having printed a summary that looks exactly like a successful run. This
# project has spent a lot of effort removing failures that look like
# successes; shipping a new one in the entrypoint would be perverse.
#
# The check is deliberately crude: is /artifacts a mount point. It is
# skipped for the subcommands that write nothing, so `doctor`, `keys` and
# `--help` still work in a bare `docker run`.

set -eu

ARTIFACTS="${OPTIONDESK_ARTIFACTS:-/artifacts}"

writes_artifacts() {
    case "${1:-}" in
        ""|doctor|keys|-h|--help|--version) return 1 ;;
        *) return 0 ;;
    esac
}

if writes_artifacts "${1:-}"; then
    if ! mountpoint -q "$ARTIFACTS" 2>/dev/null \
       && [ "$(ls -A "$ARTIFACTS" 2>/dev/null | wc -l)" -eq 0 ]; then
        cat >&2 <<'WARN'
No volume is mounted at /artifacts.

Every command here writes a schema-validated JSON artifact, and that is the
output you came for: the chain snapshot, the Greek ladder, the positioning,
the plans, the simulation and the backtests. Without a mount they are
written inside this container and lost when it exits, while the summary on
stdout looks exactly like a successful run.

Mount a directory and run it again:

  docker run --rm -v "$PWD/artifacts:/artifacts" IMAGE chain SPY

To serve the dashboard over artifacts you already have:

  docker run --rm -p 8787:8787 -v "$PWD/artifacts:/artifacts" IMAGE \
      dashboard --host 0.0.0.0

Set OPTIONDESK_ALLOW_EPHEMERAL=1 if you genuinely want a throwaway run.
WARN
        if [ "${OPTIONDESK_ALLOW_EPHEMERAL:-0}" != "1" ]; then
            exit 64
        fi
        echo "OPTIONDESK_ALLOW_EPHEMERAL is set: continuing, and the" >&2
        echo "artifacts from this run will be discarded." >&2
    fi
fi

exec optiondesk "$@"
