# Inventory Audit Tool — TASK-001

A small asset-inventory checker written with the Python standard library
only (no third-party dependencies). It was built as the first real
development task in the ChatGPT + Muse collaboration experiment
(repository `Bin1999-Mo/ai-collab-lab`, branch `feat/inventory-audit-v1`).

## What it checks

Input is a JSON list of assets, each with the required fields
`name`, `ip` and `type`:

```json
[
  {"name": "web-server-01", "ip": "192.168.10.11", "type": "server"},
  {"name": "db-server-01", "ip": "2001:db8::10", "type": "server"}
]
```

The tool reports:

| issue_type      | Meaning                                                        |
|-----------------|----------------------------------------------------------------|
| `empty_name`    | Asset name is present but empty/blank                          |
| `invalid_ip`    | IP is not a valid IPv4 or IPv6 address                         |
| `duplicate_ip`  | Same IP used by more than one asset (compared after normalisation, so different spellings of one IPv6 address also count) |
| `missing_field` | A required field (`name` / `ip` / `type`) is absent, null, or (for `type`) empty |
| `invalid_record`| A list entry is not a JSON object                              |
| `invalid_json`  | The input file is not valid JSON, or its top level is not a list |

## Usage

```bash
cd inventory-audit

# Print the report to stdout
python3 inventory_audit.py sample_assets.json

# Write the report to a file
python3 inventory_audit.py sample_assets.json -o sample_report.json
```

Exit codes: `0` = no issues found, `1` = at least one issue found
(including invalid JSON input), `2` = input file could not be read.

## Report format

```json
{
  "total_assets": 7,
  "issue_count": 5,
  "issues": [
    {
      "index": 2,
      "asset_name": null,
      "field": "name",
      "issue_type": "empty_name",
      "message": "asset name is empty"
    }
  ]
}
```

- `total_assets` — how many assets were scanned
- `issue_count` — how many problems were found
- `issues` — the detailed list; `index` is the 0-based position of the
  asset in the input list

## Sample data

`sample_assets.json` is fully fictional test data (private/documentation
address ranges only). It contains 7 assets with 5 planted problems:
one empty name, two duplicate IPs (one IPv4, one IPv6), one invalid IP
and one missing field. `sample_report.json` is the actual output of
running the tool on it.

## Running the tests

```bash
cd inventory-audit
python3 -m unittest -v test_inventory_audit
```

The tests use `unittest` from the standard library and cover: valid
data, valid IPv6, duplicate IPv4, duplicate IPv6 across different
textual representations, invalid IPs, missing fields, empty names,
invalid JSON input, a non-list top level, and the CLI exit codes and
report file output.

See `TEST_RECORD.md` for the recorded test runs of this delivery.
