# Privacy

Last updated 2026-08-31.

## The short version

This software collects nothing about you, sends nothing about you
anywhere, and has no servers. There is no telemetry, no analytics, no
crash reporting, no licence check and no phone-home of any kind.

That is not a policy promise you have to take on trust. The engine has no
network access at all, and the only outbound requests the shell makes are
to the market data provider you asked it to use.

## What runs where

Everything runs on your own machine. The command line tools, the analytics
engine, the MCP server and the dashboard are all local processes started by
you. The dashboard binds to 127.0.0.1 and serves a vendored copy of its
charting library, so loading it makes no third-party request.

## What leaves your machine

One thing: a request to a market data provider, containing the symbol and
expiry you asked about. That request goes directly from your machine to
that provider under their terms and their privacy policy, not through any
service of ours.

By default that provider is Yahoo. If you configure another, requests go
there instead. `optiondesk doctor` lists which providers are configured.

## What is stored on your machine

Artifacts, in `~/TradingDesk/option-desk` unless you point
`OPTIONDESK_ARTIFACTS` elsewhere. These are JSON files containing market
data, computed analytics, and any thesis text you chose to write when
opening a paper position. They stay on your disk. Nothing uploads them.

Replaced artifacts move to an `archive/` subdirectory rather than being
deleted, so your own history accumulates locally until you remove it.
Nothing prunes it for you.

Provider credentials, if you add any, live in `~/.optiondesk/config.env`,
outside any repository and readable only by you. They are never printed in
full, never logged, and never written into an artifact. Every release is
scanned for anything key-shaped and the build fails if something is found.

## What we receive

Nothing. There is no account, no registration, no licence server and no
usage reporting. The author has no way to know that you installed this, let
alone what you looked at.

If you open a GitHub issue, that is a public post on GitHub under their
privacy policy, and it contains whatever you choose to put in it. Please do
not put credentials or account numbers in one. See `SECURITY.md` for how to
report something privately, and note the rule in `CODE_OF_CONDUCT.md`: you
will not be asked where you are or what your network looks like.

## When an AI agent is driving

This software is designed to be invoked by an agent such as Claude Code,
Codex or ChatGPT. When it is, the artifacts it produces and the summaries
it writes pass through that agent, and the agent's own privacy policy
governs what happens to that conversation. That is a property of the agent
you chose, not of this software, and it is worth understanding before you
point one at anything sensitive.

## Children

This is a tool for analysing listed options. It is not directed at children
and collects nothing from anyone.

## Changes

Any change to this document will appear in this repository's history, with
the date above updated. There is no mailing list to notify because there is
no list of users to notify.

## Contact

Through this repository, on GitHub.
