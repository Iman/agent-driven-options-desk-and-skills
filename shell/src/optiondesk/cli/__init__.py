"""Command line entry points.

Each command does one thing, writes one schema-validated artifact, and
prints a short JSON summary to stdout. The summary is what an agent reads;
the artifact is what the dashboard and later steps read. Both carry the same
provenance and the same disclaimer.
"""
