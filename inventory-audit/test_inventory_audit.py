#!/usr/bin/env python3
"""Unit tests for inventory_audit (TASK-001). Standard library only.

Run from this directory with:
    python -m unittest -v test_inventory_audit
or from the repository root with:
    python -m unittest discover -s inventory-audit -v
"""

import json
import os
import tempfile
import unittest

import inventory_audit


def types_of(report):
    return [issue["issue_type"] for issue in report["issues"]]


class ValidateAssetsTests(unittest.TestCase):
    def test_valid_assets_have_no_issues(self):
        assets = [
            {"name": "web-server-01", "ip": "192.168.10.11", "type": "server"},
            {"name": "db-server-01", "ip": "2001:db8::10", "type": "server"},
            {"name": "printer-01", "ip": "10.0.0.25", "type": "printer"},
        ]
        report = inventory_audit.build_report(assets)
        self.assertEqual(report["total_assets"], 3)
        self.assertEqual(report["issue_count"], 0)
        self.assertEqual(report["issues"], [])

    def test_duplicate_ipv4_detected(self):
        assets = [
            {"name": "a", "ip": "192.168.1.10", "type": "server"},
            {"name": "b", "ip": "192.168.1.10", "type": "workstation"},
        ]
        report = inventory_audit.build_report(assets)
        self.assertEqual(report["issue_count"], 1)
        self.assertEqual(types_of(report), ["duplicate_ip"])
        self.assertEqual(report["issues"][0]["index"], 1)

    def test_duplicate_ipv6_across_representations_detected(self):
        assets = [
            {"name": "a", "ip": "2001:db8::1", "type": "server"},
            {"name": "b", "ip": "2001:0db8:0000:0000:0000:0000:0000:0001",
             "type": "server"},
        ]
        report = inventory_audit.build_report(assets)
        self.assertEqual(types_of(report), ["duplicate_ip"])

    def test_invalid_ip_detected(self):
        assets = [
            {"name": "bad-1", "ip": "999.168.1.1", "type": "server"},
            {"name": "bad-2", "ip": "not-an-ip", "type": "server"},
            {"name": "bad-3", "ip": "", "type": "server"},
        ]
        report = inventory_audit.build_report(assets)
        self.assertEqual(report["issue_count"], 3)
        self.assertEqual(types_of(report), ["invalid_ip"] * 3)

    def test_missing_field_detected(self):
        assets = [
            {"name": "no-ip", "type": "server"},
            {"ip": "10.0.0.1", "type": "server"},
            {"name": "no-type", "ip": "10.0.0.2"},
        ]
        report = inventory_audit.build_report(assets)
        missing = [i for i in report["issues"]
                   if i["issue_type"] == "missing_field"]
        self.assertEqual(len(missing), 3)
        self.assertEqual({i["field"] for i in missing},
                         {"ip", "name", "type"})

    def test_empty_name_detected(self):
        assets = [
            {"name": "", "ip": "10.0.0.1", "type": "server"},
            {"name": "   ", "ip": "10.0.0.2", "type": "server"},
        ]
        report = inventory_audit.build_report(assets)
        self.assertEqual(report["issue_count"], 2)
        self.assertEqual(types_of(report), ["empty_name", "empty_name"])

    def test_ipv6_valid_addresses_accepted(self):
        assets = [
            {"name": "v6-a", "ip": "::1", "type": "server"},
            {"name": "v6-b", "ip": "fe80::1ff:fe23:4567", "type": "switch"},
        ]
        report = inventory_audit.build_report(assets)
        self.assertEqual(report["issue_count"], 0)


class FileInputTests(unittest.TestCase):
    def _write_temp(self, text):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_invalid_json_input_raises_and_audits_as_invalid_json(self):
        path = self._write_temp("{ this is not json ]")
        with self.assertRaises(inventory_audit.InventoryLoadError):
            inventory_audit.load_assets(path)
        report = inventory_audit.audit_file(path)
        self.assertEqual(report["total_assets"], 0)
        self.assertEqual(report["issue_count"], 1)
        self.assertEqual(types_of(report), ["invalid_json"])

    def test_top_level_not_a_list_is_invalid(self):
        path = self._write_temp('{"name": "x", "ip": "10.0.0.1"}')
        with self.assertRaises(inventory_audit.InventoryLoadError):
            inventory_audit.load_assets(path)

    def test_cli_writes_report_and_exits_1_when_issues_found(self):
        input_path = self._write_temp(json.dumps([
            {"name": "a", "ip": "10.0.0.1", "type": "server"},
            {"name": "b", "ip": "10.0.0.1", "type": "server"},
        ]))
        fd, output_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.addCleanup(
            lambda: os.path.exists(output_path) and os.remove(output_path))
        exit_code = inventory_audit.main([input_path, "-o", output_path])
        self.assertEqual(exit_code, 1)
        with open(output_path, "r", encoding="utf-8") as handle:
            report = json.load(handle)
        self.assertEqual(report["total_assets"], 2)
        self.assertEqual(report["issue_count"], 1)
        self.assertEqual(types_of(report), ["duplicate_ip"])

    def test_cli_exits_0_for_clean_inventory(self):
        input_path = self._write_temp(json.dumps([
            {"name": "a", "ip": "10.0.0.1", "type": "server"},
        ]))
        exit_code = inventory_audit.main([input_path])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
