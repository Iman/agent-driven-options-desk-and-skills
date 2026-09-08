# Screenshot provenance

[README](../README.md) · [Gallery](SCREENSHOTS.md) · [Dashboard guide](wiki/Dashboard.md)

## Current capture

| Field | Recorded value |
|---|---|
| Capture time | 2026-09-08T22:32:48+00:00, from the comparison image's filesystem timestamp |
| Application source | `9626273b5ea0f3374c48d3424605a57377473359` |
| Renderer | The repository's current local dashboard and Playwright Chromium |
| Input directory | `examples/dashboard` |
| Selection | `SYNTH`, expiry `2026-10-08` |
| Gallery viewport | 1,600 pixels wide |
| README viewport | 1,400 pixels wide |
| Output | 100 PNG images: one full page, 15 sections, 42 panels, 32 charts, and 10 README views |

The capture uses synthetic teaching inputs throughout.
The application source revision identifies the code used to render these images.
The documentation changes do not alter that application code.

The [manifest](screenshot-manifest.json) records SHA-256 hashes for every image and every supplied JSON input or artifact.
The sample files carry their own fixed scenario date, separate from the screenshot capture time.

## What the images establish

The images show how the current dashboard renders the supplied artifacts.
They demonstrate layout, navigation, chart coverage, and displayed explanations.
They do not establish live-provider availability, pricing accuracy against a market, or strategy performance.

The capture uses real browser screenshots of the running local interface.

## Input origin

The near and far chains use authored spot, rates, volatility, bid/ask offsets, volume, and open interest.
The underlying history is an authored random series.
No provider data or private positions were used in this capture.
The [sample guide](../examples/README.md) records the construction and limitations.
Absolute source paths in the example artifacts were replaced with repository-relative paths for portability.

The saved artifacts retain calculation results and diagnostics from the normal command implementations.
Their source notes identify synthetic inputs.
The backtest honesty text explicitly identifies synthetic history instead of claiming real historical observations.

## Recapture

After installing the local tools and Playwright, run:

```sh
python scripts/screenshots.py --artifacts examples/dashboard --underlying SYNTH --expiry 2026-10-08 --note "Synthetic teaching inputs. No observed market data."
```

See [Development](wiki/Development.md#capture-the-dashboard) for the installation commands.
After a new capture, update the date, revision, and hashes here and in the manifest.
Do not relabel a recapture of saved inputs as fresh market data.

## Previous gallery

The previous committed gallery came from revision `ac72957` on September 3, 2026.
Its captions described a SPY provider-data run.
The current gallery replaces those images with a supplied synthetic scenario.
Historical captures remain in Git history; they are not current evidence.
