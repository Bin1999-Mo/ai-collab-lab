#!/usr/bin/env python3
"""Asset inventory audit tool (TASK-001).

Reads a JSON asset inventory where every asset is an object with the
required fields ``name``, ``ip`` and ``type``, and reports:

- assets whose ``name`` is empty,
- assets whose ``ip`` is not a valid IPv4 or IPv6 address,
- duplicate IP addresses (compared after normalisation, so different
  textual representations of the same IPv6 address count as duplicates),
- assets with missing required fields,
- input that is not valid JSON or not a JSON list at all.

Only the Python standard library is used.

Usage:
    python inventory_audit.py assets.json [-o report.json]

Exit codes:
    0  the inventory was read and no issues were found
    1  the inventory was read and at least one issue was found
       (an invalid-JSON or non-UTF-8 input is reported as a single
       ``invalid_json`` issue and also exits with 1)
    2  a file error: the input file could not be read at all (e.g. it
       does not exist), the report could not be written (e.g. the
       output directory does not exist), or the output path is the
       same file as the input path (overwriting the input is refused,
       including through a symbolic link)
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys

REQUIRED_FIELDS = ("name", "ip", "type")


class InventoryLoadError(ValueError):
    """Raised when the inventory file is not valid JSON asset data."""


def _issue(index, asset_name, field, issue_type, message):
    return {
        "index": index,
        "asset_name": asset_name,
        "field": field,
        "issue_type": issue_type,
        "message": message,
    }


def _normalised_ip(value):
    """Return the canonical string form of a valid IP, else None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return str(ipaddress.ip_address(text))
    except ValueError:
        return None


def validate_assets(assets):
    """Validate a list of asset dicts and return a list of issue dicts."""
    issues = []
    seen_ips = {}  # normalised ip -> (first index, first asset name)

    for index, record in enumerate(assets):
        if not isinstance(record, dict):
            issues.append(
                _issue(index, None, None, "invalid_record",
                       "asset entry is not a JSON object")
            )
            continue

        raw_name = record.get("name")
        asset_name = raw_name if isinstance(raw_name, str) and raw_name.strip() else None

        # Missing required fields: key absent or value is None.
        for field in REQUIRED_FIELDS:
            if field not in record or record[field] is None:
                issues.append(
                    _issue(index, asset_name, field, "missing_field",
                           f"required field '{field}' is missing")
                )

        # Empty asset name (present but blank or not a string).
        if "name" in record and record["name"] is not None:
            if not isinstance(record["name"], str) or not record["name"].strip():
                issues.append(
                    _issue(index, None, "name", "empty_name",
                           "asset name is empty")
                )

        # Empty type is treated as a missing field.
        if isinstance(record.get("type"), str) and not record["type"].strip():
            issues.append(
                _issue(index, asset_name, "type", "missing_field",
                       "required field 'type' is empty")
            )

        # A present, non-null type must be a string (numbers, booleans,
        # lists etc. are rejected with their own issue type).
        if "type" in record and record["type"] is not None \
                and not isinstance(record["type"], str):
            issues.append(
                _issue(index, asset_name, "type", "invalid_field_type",
                       f"field 'type' must be a non-empty string, "
                       f"got {type(record['type']).__name__}: "
                       f"{record['type']!r}")
            )

        # IP format and duplicates (only when an ip value is present).
        if "ip" in record and record["ip"] is not None:
            normalised = _normalised_ip(record["ip"])
            if normalised is None:
                issues.append(
                    _issue(index, asset_name, "ip", "invalid_ip",
                           f"invalid IP address: {record['ip']!r}")
                )
            elif normalised in seen_ips:
                first_index, first_name = seen_ips[normalised]
                issues.append(
                    _issue(index, asset_name, "ip", "duplicate_ip",
                           f"duplicate IP address {normalised}: first seen at "
                           f"index {first_index} (asset {first_name!r})")
                )
            else:
                seen_ips[normalised] = (index, asset_name)

    return issues


def build_report(assets):
    """Build the JSON report dict for an already-parsed asset list."""
    issues = validate_assets(assets)
    return {
        "total_assets": len(assets),
        "issue_count": len(issues),
        "issues": issues,
    }


def load_assets(path):
    """Load and parse the inventory file.

    Raises InventoryLoadError if the file content is not valid UTF-8,
    not valid JSON, or the top-level JSON value is not a list.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except UnicodeDecodeError as exc:
        raise InventoryLoadError(f"invalid UTF-8 input: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InventoryLoadError(f"invalid JSON input: {exc}") from exc
    if not isinstance(data, list):
        raise InventoryLoadError(
            "invalid inventory format: top-level JSON value must be a list"
        )
    return data


def audit_file(path):
    """Audit an inventory file and return the report dict.

    Invalid JSON input does not raise; it produces a report with a
    single ``invalid_json`` issue so callers always get JSON out.
    """
    try:
        assets = load_assets(path)
    except InventoryLoadError as exc:
        return {
            "total_assets": 0,
            "issue_count": 1,
            "issues": [_issue(None, None, None, "invalid_json", str(exc))],
        }
    return build_report(assets)


def _is_same_file(path_a, path_b):
    """True if two paths refer to the same file.

    Symbolic links are resolved, and when both paths exist the
    filesystem identity (device + inode) is compared as well, so a
    symlink or hard link to the input is recognised.
    """
    if os.path.realpath(path_a) == os.path.realpath(path_b):
        return True
    try:
        return os.path.exists(path_a) and os.path.exists(path_b) \
            and os.path.samefile(path_a, path_b)
    except OSError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Audit a JSON asset inventory for naming, IP and "
                    "required-field problems."
    )
    parser.add_argument("input", help="path to the JSON asset inventory")
    parser.add_argument("-o", "--output",
                        help="write the JSON report to this file "
                             "(default: print to stdout)")
    parser.add_argument("--indent", type=int, default=2,
                        help="JSON indentation level (default: 2)")
    args = parser.parse_args(argv)

    # Refuse to overwrite the input file, including via a symlink or
    # another path that resolves to the same file.
    if args.output and _is_same_file(args.input, args.output):
        print(f"error: output path {args.output!r} is the same file as "
              f"the input; refusing to overwrite the input inventory",
              file=sys.stderr)
        return 2

    try:
        report = audit_file(args.input)
    except OSError as exc:
        print(f"error: cannot read input file: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(report, ensure_ascii=False, indent=args.indent)
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError as exc:
            print(f"error: cannot write report to {args.output!r}: {exc}",
                  file=sys.stderr)
            return 2
    else:
        print(text)
    return 0 if report["issue_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
