# Licensing map

This repository ships two separately licensed components. The boundary is a
directory boundary, and it is deliberate. Read this file before copying any
code out of the tree.

## shell/ is MIT

Everything under `shell/` is MIT licensed. That covers the skill documents,
the JSON contracts and schemas, the provider registry and its free data
providers, the CLI plumbing, the MCP server and the dashboard. The intent is
that anyone can take the shell, embed it, fork it, or ship it inside a
commercial product without asking permission.

The shell contains no proprietary modelling. It fetches data, validates it
against a schema, writes artifacts, and exposes those artifacts to agent
runtimes and to a browser.

## engine/ is AGPL-3.0

Everything under `engine/` is licensed under the GNU Affero General Public
License version 3. That covers the pricing and Greek analytics, and it will
cover the volatility surface, the variance risk premium work, the dealer
gamma analytics, the Monte Carlo and MCMC engines and the backtester as they
are ported in.

The practical effect of AGPL section 13: if you run a modified version of the
engine as a network service, you must offer the source of your modified
version to the users of that service. Running it privately for yourself
carries no such obligation.

## Commercial licensing of the engine

The copyright in the engine is held by Iman Samizadeh. AGPL is offered as one
option. A separate commercial licence, which removes the AGPL obligations, is
available on request. Dual licensing only remains possible while every line in
`engine/` is either originally authored here or received under a permissive
licence, which leads to the two standing rules below.

## Two standing rules

1. No third-party GPL or AGPL code enters `engine/`. Third-party copyleft
   cannot be relicensed by this project, and its presence would end the
   ability to grant commercial licences. Permissively licensed third-party
   code (MIT, BSD, Apache-2.0) is acceptable with attribution recorded in
   THIRD-PARTY.md.
2. No code of unknown provenance enters either component. A public repository
   with no licence file is not permissively licensed. It is all rights
   reserved by default, and it stays out.

## Contributions

Outside contributions to `engine/` require a signed contributor licence
agreement before merge. See CLA.md. Without it the project cannot offer
commercial licences covering the contributed lines.

## Data is not code

A licence on this software grants no rights over any market data it retrieves.
Data redistribution rights are governed by each data provider's own terms.
See DISCLAIMER.md.
