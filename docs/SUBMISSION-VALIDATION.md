# Submission validation: hosted service 0.3.1

Validated on 5 September 2026. Technical status: HOLD — ChatGPT template loading remains unresolved.
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
- Production health requests completed in 70–176 ms during that check.
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
