# Development and documentation maintenance

[Guide home](Home.md) | [Architecture](Architecture.md) | [Contributing](../../CONTRIBUTING.md)

## Prepare an environment

From a checkout, create and activate a virtual environment as described in [Getting started](Getting-Started.md).
Then install the development packages:

```sh
python -m pip install -e ./engine -e './shell[dev]' -e './agent[dev]'
python -m playwright install chromium
python -m pytest -q --color=no
```

Read the actual test summary. Collection counts do not establish a passing run.
Some server tests bind a loopback port and need an environment that permits it.

## Test layers and coverage

Use the [testing guide](../TESTING.md) for unit, BDD, integration, and validation commands.
Unit coverage must reach 80% of executable lines in each Python package.
BDD and integration coverage do not count toward that minimum.
The guide includes success and failure scenarios and the TDD procedure.

## Regenerate derived files

```sh
python3 scripts/refresh.py --no-index
```

This command rebuilds generated files and runs the configured checks.
Use `--fast` only when you intend to skip the suites.
Read every stage result before claiming that the refresh passed.

Edit local skills in `shell/skills/` and hosted skills in `openai-skills/`.
Do not edit generated plugin copies or runtime documents directly.

## Documentation checks

```sh
python -m pytest shell/tests/test_screenshots.py shell/tests/test_documented_counts.py shell/tests/test_documented_evidence.py -q
python3 scripts/evidence.py check
git diff --check
```

The screenshot checks catch broken references and orphaned images.
The count checks compare documented inventories with the current source.
The evidence check preserves the relationship between historical figures and their recorded origin.

## Capture the dashboard

The supplied `examples/dashboard` directory contains synthetic artifacts for the full visual tour.
The interactive walkthrough builds a smaller set from `examples/chain-synth.json`.

Install the browser capture tools in the active environment:

```sh
python -m pip install playwright
python -m playwright install chromium
```

Run the existing capture script:

```sh
python scripts/screenshots.py --artifacts examples/dashboard --underlying SYNTH --expiry 2026-10-08 --note "Synthetic teaching inputs. No observed market data."
```

The script starts a local dashboard, captures its DOM elements, and writes the gallery and README images.
It does not fetch market data.
Check the resulting images at full size before committing them.
Record the capture date, code revision, and input hashes in [screenshot provenance](../SCREENSHOT-PROVENANCE.md).

Some captions reflect the supplied scenario, such as its contract count.
If a new capture changes filenames, remove obsolete captures only after updating their references.

## Wiki source and publication

The editable guide pages live in `docs/wiki/`.
They use relative Markdown links so the guide also works in a repository checkout.
The sidebar and footer live beside the pages.

The GitHub wiki is a separate Git repository.
Before its first Git publication, create its initial page through GitHub's web interface.
See [GitHub's wiki instructions](https://docs.github.com/en/communities/documenting-your-project-with-wikis/adding-or-editing-wiki-pages).

When exporting these pages to that repository:

1. Convert sibling guide links to wiki page URLs without the `.md` suffix.
2. Convert repository-document links to the corresponding `blob/main` URLs.
3. Convert image links to the corresponding `raw.githubusercontent.com` URLs.
4. Include `_Sidebar.md` and `_Footer.md`.
5. Check the rendered home page, navigation, code blocks, and images.

Keep the repository pages as the editable source.
Record the published revision and preserve unrelated wiki pages during updates.

Next: [Documentation map](Documentation-Map.md).
