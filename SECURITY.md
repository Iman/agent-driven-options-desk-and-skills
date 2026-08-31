# Security

## Reporting a vulnerability

Report privately, not as a public issue. Use GitHub's private vulnerability
reporting on this repository, under Security, Report a vulnerability.

Tell me what you did, what happened, and what you expected. A reproduction
is worth more than a description. I will confirm receipt, and I will tell
you plainly if I disagree that something is a vulnerability rather than
letting the report go quiet.

## What is in scope

The installer, because it runs a shell script fetched over the network and
writes into your home directory. The MCP server, because it accepts input
from a model. The provider layer, because it parses third-party responses.
The artifact writer, because it decides what reaches disk.

Two specific classes I care about, having already fixed one of each:

- Anything that makes the installer write outside the directories it
  declares, or delete something it did not create. A bare `owner/name` in
  the repository field once resolved to a local path, so the one-line
  install could be made to install a planted directory instead.
- Anything that makes a tool call reach outside its advertised arguments.
  The MCP server whitelists arguments against the schema it publishes for
  exactly this reason.

## What is not in scope

Market data being wrong, delayed or missing. That is the provider's, and
the software reports it rather than hiding it.

Losing money. This is research software and it places no orders. See
DISCLAIMER.md.

The absence of authentication. Everything here runs locally as you, and the
dashboard binds to 127.0.0.1 deliberately. If you expose it to a network,
that is a decision you have made and its consequences are yours.

## What this software does with your data

It writes artifacts to your disk and reads them back. It fetches market
data from whichever provider answers. It sends nothing about you or your
usage anywhere.

Provider credentials live in `~/.optiondesk/config.env`, outside any
repository, readable only by you. They are never printed in full, never
logged, and never written into an artifact. A refresh scans every tracked
file for anything key-shaped and fails if it finds one.
