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


class ReviewRegressionTests(unittest.TestCase):
    """Regression tests for the four defects found in ChatGPT's
    independent review of the first TASK-001 delivery (commit 9b4a2037).
    """

    def _write_temp(self, text):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    # P1: -o must never overwrite the input file.
    def test_output_same_as_input_is_refused_and_input_unchanged(self):
        content = json.dumps(
            [{"name": "a", "ip": "10.0.0.1", "type": "server"}])
        input_path = self._write_temp(content)
        exit_code = inventory_audit.main([input_path, "-o", input_path])
        self.assertEqual(exit_code, 2)
        with open(input_path, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), content)

    # P1 (symlink case): an output path that is a symlink to the input
    # must be refused as well.
    def test_output_symlink_to_input_is_refused(self):
        content = json.dumps(
            [{"name": "a", "ip": "10.0.0.1", "type": "server"}])
        input_path = self._write_temp(content)
        link_path = input_path + ".link.json"
        try:
            os.symlink(input_path, link_path)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not available on this platform")
        self.addCleanup(
            lambda: os.path.islink(link_path) and os.remove(link_path))
        exit_code = inventory_audit.main([input_path, "-o", link_path])
        self.assertEqual(exit_code, 2)
        with open(input_path, "r", encoding="utf-8") as handle:
            self.assertEqual(handle.read(), content)

    # P2: writing to a non-existent output directory must produce a
    # controlled exit code 2, not an exception traceback.
    def test_output_to_missing_directory_returns_2(self):
        input_path = self._write_temp(json.dumps(
            [{"name": "a", "ip": "10.0.0.1", "type": "server"}]))
        bad_output = os.path.join(
            tempfile.gettempdir(), "no-such-dir-task001-xyz", "report.json")
        exit_code = inventory_audit.main([input_path, "-o", bad_output])
        self.assertEqual(exit_code, 2)
        self.assertFalse(os.path.exists(bad_output))

    # P2 (encoding): invalid UTF-8 bytes must be handled like other
    # controlled input errors: a single invalid_json report issue and
    # CLI exit code 1, with no UnicodeDecodeError escaping.
    def test_invalid_utf8_input_is_controlled(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "wb") as handle:
            handle.write(b'[{"name": "\xff\xfe", "ip": "10.0.0.1"}]')
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        report = inventory_audit.audit_file(path)
        self.assertEqual(report["issue_count"], 1)
        self.assertEqual(types_of(report), ["invalid_json"])
        self.assertIn("UTF-8", report["issues"][0]["message"])
        self.assertEqual(inventory_audit.main([path]), 1)

    # P3: a non-string type (number, boolean, list) must be rejected
    # with the dedicated invalid_field_type issue type.
    def test_non_string_type_detected(self):
        assets = [
            {"name": "a", "ip": "10.0.0.1", "type": 123},
            {"name": "b", "ip": "10.0.0.2", "type": True},
            {"name": "c", "ip": "10.0.0.3", "type": ["server"]},
        ]
        report = inventory_audit.build_report(assets)
        self.assertEqual(report["issue_count"], 3)
        self.assertEqual(types_of(report), ["invalid_field_type"] * 3)
        self.assertTrue(
            all(i["field"] == "type" for i in report["issues"]))

    # P3 (control): ordinary string types keep working, and an empty
    # string type is still reported as a missing field.
    def test_string_and_empty_type_behaviour_unchanged(self):
        assets = [
            {"name": "a", "ip": "10.0.0.1", "type": "server"},
            {"name": "b", "ip": "10.0.0.2", "type": ""},
        ]
        report = inventory_audit.build_report(assets)
        self.assertEqual(report["issue_count"], 1)
        self.assertEqual(types_of(report), ["missing_field"])
        self.assertEqual(report["issues"][0]["index"], 1)


if __name__ == "__main__":
    unittest.main()
