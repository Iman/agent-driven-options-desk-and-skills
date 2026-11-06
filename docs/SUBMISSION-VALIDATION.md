# Option Desk submission validation

## Plugin version update, 6 November 2026

The portal reported version 0.3.0 as already published. The package generator,
generated manifests and submission import now use 0.3.1. The existing package ID
and MCP URL remain unchanged, and the ZIP still omits the auth override.
Portal acceptance of this version remains UNKNOWN.

## Existing MCP connection update, 6 November 2026

The maintainer supplied a portal finding that the existing app already has
authentication configured and the ZIP must omit its auth override. The generator
now omits `extensions.com.openai.auth` from the referenced `.mcp.json`.
The package ID, version and MCP URL remain unchanged. Authentication changes
belong in the existing app's portal settings. Portal acceptance remains UNKNOWN.

VERIFIED: two packaging regressions failed with the override present. After its
removal, all 37 packaging and house-rule checks passed. CLOSED for the packaged
auth override; the server runtime was not changed by this package correction.

## Pre-release validation record, 6 November 2026

This section records the earlier draft before deployment. Its auth declaration
is superseded by the existing-connection update above.

UNKNOWN: legal enforceability and regulatory applicability remain for qualified
review. The revised hosted controls have not been deployed. Portal acceptance,
review conversations, identity/domain verification and production rendering have
not been checked for this draft. Repository ownership and upstream licences remain
unchanged. Do not treat this record as a compliance attestation.

VERIFIED: the hosted suite executed 83 tests and passed. The public
packaging and house-rule checks executed 37 tests and passed.
Both browser acknowledgement and data-permission regressions are covered by the
hosted checks. Synthetic demos remain available.

The rebuilt hosted ZIP has 11 files and 4 skills. Every archived file matches
its current source, the archive integrity check passes, and the MCP server declares
`extensions.com.openai.auth.type: "none"`, following the
[authentication reference](https://developers.openai.com/plugins/build/plugins#configure-mcp-authentication).
The import JSON matches its canonical private-repository copy and validates against
the [official schema](https://developers.openai.com/plugins/schemas/chatgpt-app-submission.v1.json).
All 13 tool names and declared annotation values match the local hosted registry.
The import contains 5 positive and 5 negative review specifications. These are not
completed conversation tests.

Artifact digests, byte counts and the check timestamp are in
`dist/option-desk-openai-validation.json`. The schema copy is
`dist/chatgpt-app-submission.schema.json`. Upload the import JSON, not the schema.
No commit, push, deployment or submission accompanies these local changes.

## Existing listing identity correction

The maintainer reported the public listing's package ID as
`app-6a9928feca1c8191aa083ed88feb1e54`. The generated Codex manifest,
Codex marketplace and ZIP now use that ID. Three assertions failed before
the correction and passed afterward. Claude's plugin name remains unchanged.
Directory acceptance of the rebuilt ZIP remains unverified.

## Historical record, before these draft changes

The dated evidence below describes earlier builds. Its production and test claims
must not be read as verification of the current working tree.

# Submission validation: hosted service 0.3.1

Validated on 5 September 2026. Technical status: HOLD: ChatGPT template loading remains unresolved.
This is an engineering assessment, not approval from the directory reviewer.

## Deployed build

- Endpoint: https://optiondesk.avidquant.com/mcp
- Service version: 0.3.1
- Image: avidquant/optiondesk-hosted:submission-0.3.1-errors
- Image digest: sha256:ec12c6e8666ab928efda066e92cee8f634d68d74394dd7fa05594bf443cd5415
- Previous container retained for rollback.

## Completed checks

- 56 server tests passed, including synthetic and user-supplied reports, upload consent and retention checks, and non-blocking rendering.
- 8 widget tests passed, including initialization, missing-data timeout, late delivery and message-source checks.
- 20 package tests passed with no skips. Both hosted archives were rebuilt.
- Three concurrent production reports using human-readable strategy names each returned six valid PNGs and correct strategy records.
- Production health requests completed in 70-176 ms during that check.
- Four invalid report requests were rejected: a live ticker without input data, an unknown strategy, too many strategies, and duplicate aliases.
- Current and both legacy widget resource URLs respond. The current URI is ui://optiondesk/plot-v3.html.
- All widget resources declare a unique origin and empty network/resource CSP allowlists.
- Website, support, privacy and terms pages respond successfully.
- Before the strategy-name fix, two fresh report calls were checked in the existing Chrome test conversation. The final call displayed all six decoded images.
- The final ChatGPT response used engine records, left currency and contract multiplier unspecified, and reported the correct cost ratios.

The recording failure with `iron condor` is fixed. Spaces, hyphens and equivalent
strategy names now resolve to canonical IDs. Unknown names still fail explicitly.
The updated build passed endpoint checks; repeat the recording prompt to confirm
rendering in the recording session.

## Correct numerical conventions

Strategy legs and values come from the same engine records as the payoff charts.
All strategy values are per underlying unit and weighted by leg quantity.
No currency or contract multiplier is implied.
Vega per volatility percentage point equals raw vega divided by 100.

Full bid/ask entry cost differs from modeled patient-fill entry cost.
The default patient-fill model concedes 0.5 of each half-spread.
Under this assumption, full-crossing entry equals modeled round-trip cost.

| Structure | Mid cash | Natural cash | Natural entry cost | Model entry | Model round trip |
|---|---:|---:|---:|---:|---:|
| Iron condor | 1.80 | 1.48 | 0.32 | 0.16 | 0.32 |
| Bull put spread | 0.90 | 0.74 | 0.16 | 0.08 | 0.16 |
| Straddle | -9.20 | -9.36 | 0.16 | 0.08 | 0.16 |

## Open recording issue

The user subsequently reported “Failed to fetch template” and a widget timeout.
Rejected plot calls now supply structured error data. The widget handles host
cancellation, and status explicitly rules out hosted backtests after history uploads.
Server and widget regression checks pass. Chrome inspection is disconnected;
the current recording session must pass a fresh rendering check before clearance.

## Submission handoff

Record a clean demonstration using the refreshed connection and bundled report tool.
Complete publisher identity, domain verification and the portal evidence fields.
Scan the deployed endpoint so the portal receives the current tool schemas and widget metadata.
These publisher-controlled steps and the platform review decision are not certified by this test record.
