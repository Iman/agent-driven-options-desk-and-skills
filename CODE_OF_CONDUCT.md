# Code of conduct

## The short version

Be straight with people and do not be unpleasant. If you would not say it
to a colleague you respect, do not put it in an issue.

## What is expected

Technical disagreement is welcome and is most of the value of a public
repository. Bring evidence: a reproduction, a measurement, a line number.
"This is wrong" with a failing case is a gift. "This is wrong" on its own
is noise.

Assume the other person has a reason you have not heard yet, and ask before
concluding they are careless. Much of this project exists because a
confident claim turned out to be false on first contact with data.

## What is not

Personal attacks, harassment, or comments about someone's nationality,
religion, gender, sexuality, disability or background. Deliberate
misrepresentation of what someone said. Persistent argument after a
maintainer decision, which is different from disagreeing once and clearly.

Presenting this software's output as investment advice, or using an issue
thread to promote a service. That is both a conduct problem and a
regulatory one, and DISCLAIMER.md explains why.

## One rule specific to this project

**Do not ask anyone to name their country, or to describe their network
conditions.**

Not in an issue, not in a pull request review, not while diagnosing a
failure. Not "which country are you in?", not "is your ISP blocking it?",
not "can you reach GitHub directly?"

This project is about markets, and the people who find it useful are spread
across places where answering that question is anything from tedious to
dangerous. Someone debugging a failed clone should not have to choose
between getting help and disclosing where they are or how they reach the
internet. The question also tends to arrive with an assumption attached,
and the assumption is usually wrong.

It is nearly always unnecessary. Almost every question that seems to need
it has a better form:

| Do not ask | Ask instead |
|---|---|
| Which country are you in? | What is the exact error, in full? |
| Is your network blocking it? | Does `curl -sI https://pypi.org` return a status line? |
| Are you behind a proxy or VPN? | Does the failure happen with `--provider yahoo` and also without it? |
| Can you reach GitHub? | Does `git clone https://github.com/...` succeed on its own? |

The answers to the right-hand column are what actually diagnose the fault.
The left-hand column collects a fact about a person instead of a fact about
the software.

If someone volunteers where they are, that is theirs to volunteer. Do not
repeat it, and do not build it into an issue title.

## Scope and enforcement

This applies to issues, pull requests, discussions and any other space
carrying this project's name.

Report a problem to the maintainer through GitHub. Reports are handled
privately. The responses available are, in order: a request to stop, a
removal of the offending content, and a block. I will say which one I am
using and why, rather than acting silently.

I am one person maintaining this in my own time. That means slow responses,
not absent standards.
