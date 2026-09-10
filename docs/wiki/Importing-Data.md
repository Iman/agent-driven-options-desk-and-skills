# Import your option chain

[Guide home](Home.md) | [First walkthrough](Getting-Started.md) | [Examples](Examples.md)

The importer accepts CSV and JSON. Local imports read your file and write local artifacts.
A hosted upload sends the file to the separate service.

## Prepare the file

| Input | Required information |
|---|---|
| Snapshot | Underlying, spot, expiry, and data source |
| Contract row | Strike and option type |
| Useful calculations | A valid implied volatility or a price that identifies it |
| Positioning | Open interest for the contracts you want included |
| Provenance | Snapshot timestamp, rate, and dividend yield |

The complete JSON example is [chain-synth.json](../../examples/chain-synth.json).
Its values are synthetic. Do not copy its values into a market-data export.

A CSV can repeat snapshot metadata on each row:

```csv
underlying,spot,expiry,snapshot_timestamp,strike,type,bid,ask,iv,open_interest,volume
SYNTH,100,2026-10-08,2026-09-08T00:00:00Z,100,call,3.0,3.2,0.26,1000,100
SYNTH,100,2026-10-08,2026-09-08T00:00:00Z,100,put,2.8,3.0,0.26,900,80
```

This small snippet explains columns. Use the complete supplied JSON for the walkthrough.
It imports, but the result is flagged degraded because the rows carry no `risk_free_rate` or `dividend_yield`. The reason names the 0.04 default rate and the zero yield.
The `normalization` block also records one repair per row, `calculated mid from bid and ask`.
Add those two columns, or pass `--rate` and `--dividend-yield`, to clear the flag.
A two-row chain cannot demonstrate a multi-leg spread or a full volatility smile.

## Import a permitted export

Save your export as `chain.csv` in the current directory.
Replace the example symbol and source label with the actual values.

```sh
optiondesk chain SPY --from-file chain.csv --data-source "broker export" --accept-data-rights --out-dir artifacts/research
```

Only acknowledge rights when the source permits this use.
The statement does not grant rights that the provider withholds.

If your export omits rates, supply your chosen assumptions with `--rate` and `--dividend-yield`.
Both use decimal units. For example, `0.04` means four percent.
The output records those inputs and any missing-input warnings.

## Check the import

Read the JSON summary and saved chain before building a structure.

- Check the symbol, expiry, spot, source, and capture timestamp.
- Read `degraded`, its reason, and `notes`.
- Read `normalization` for format repairs and warnings.
- Inspect `counts` and the contracts without usable volatility.

The importer normalizes documented column aliases, call/put notation, numeric commas, and clear percentage units.
It rejects invalid or conflicting required fields and duplicate contracts.
It does not invent missing spot, strike, expiry, or quotes.

Zero bid and ask do not establish a usable midpoint.
An explicitly supplied valid IV can still support calculations on that row.
Read the returned counts instead of assuming all zero-quote rows have the same outcome.

## Continue from the saved snapshot

```sh
optiondesk greeks --out-dir artifacts/research
optiondesk exposure --out-dir artifacts/research
optiondesk compare --out-dir artifacts/research
optiondesk dashboard --out-dir artifacts/research
```

These examples use an isolated directory with one imported chain.
For several chains, pass the intended saved file with `--snapshot` to the calculation commands.
Use the dashboard selectors to choose the symbol and expiry.

## Recover from an import error

| Message or symptom | Action |
|---|---|
| Missing spot, expiry, or source | Add the actual value from the export source. |
| Duplicate call or put at a strike | Identify the intended contract and remove the duplicate row. |
| Mixed underlyings or expiries | Separate the export into one snapshot per underlying and expiry. |
| Missing IV and unusable quotes | Obtain usable data or accept that the contract cannot support those calculations. |
| Crossed bid and ask | Check the source. The importer does not silently swap them. |
| Missing timestamp | Supply the actual capture time. Do not describe undated data as current. |

Next: [Read the results](Reading-Results.md).
