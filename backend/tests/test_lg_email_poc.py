"""Synthetic, offline tests; no LG service, real recipient or network is used."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import ssl
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import lg_email_poc as poc  # noqa: E402


class Response:
    code = 200
    headers = {"X-Private": "sensitive-response"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return b"sensitive-response"


class LGEmailPocTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "private"
        self.workspace.mkdir()
        self.config = copy.deepcopy(poc.TEMPLATE)
        self.config.update(
            {
                "endpoint": "https://mail.corp.test/SMTP",
                "openapi_url": "https://mail.corp.test/openapi.json",
                "approved_internal_hosts": ["mail.corp.test"],
                "approved_internal_domains": ["corp.test"],
                "approved_recipients": ["one@corp.test", "two@corp.test"],
                "to": ["one@corp.test", "two@corp.test"],
                "cc": ["two@corp.test"],
                "authorization_confirmed": True,
            }
        )
        self.save_config()
        poc.write_private(self.workspace / "specification.json", {"sha256": "a" * 64})

    def save_config(self):
        (self.workspace / "config.json").write_text(
            json.dumps(self.config), encoding="utf-8"
        )

    def cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = poc.main(["--workspace", str(self.workspace), *args])
        return code, json.loads(output.getvalue())

    def send(self, case="single", response=None):
        with patch.object(
            poc, "open_request", return_value=response or Response()
        ) as call:
            result = poc.probe(self.workspace, self.config, case, send=True)
        return result, call

    def test_init_requires_configuration_and_never_overwrites(self):
        workspace = Path(self.temp.name) / "new"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(poc.main(["--workspace", str(workspace), "init"]), 0)
            self.assertEqual(poc.main(["--workspace", str(workspace), "init"]), 2)
        with self.assertRaises(poc.PocError):
            poc.load_config(workspace)

    def test_check_and_dry_run_never_open_network(self):
        with patch.object(poc, "open_request") as call:
            self.assertEqual(self.cli("check")[0], 0)
            code, result = self.cli("probe", "--case", "single")
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "dry_run_no_network")
            call.assert_not_called()
        self.assertEqual(list(self.workspace.glob("attempt-*")), [])

    def test_both_send_flags_required(self):
        for flag in ("--send", "--allow-real-send"):
            with self.subTest(flag=flag), patch.object(poc, "open_request") as call:
                self.assertEqual(self.cli("probe", "--case", "single", flag)[0], 2)
                call.assert_not_called()

    def test_multipart_unicode_and_no_files(self):
        body, content_type, _ = poc.build_message(self.config, "unicode", "marker")
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
        )
        parts = list(message.iter_parts())
        self.assertEqual(
            [p.get_param("name", header="content-disposition") for p in parts],
            ["Subject", "Body", "To"],
        )
        self.assertIn("ação 日本語", parts[0].get_payload(decode=True).decode("utf-8"))
        self.assertIn("\nLinha 2.", parts[1].get_payload(decode=True).decode("utf-8"))
        self.assertNotIn(b"filename=", body)

    def test_recipient_formats(self):
        for style, expected in (
            ("comma", "a,b"),
            ("semicolon", "a;b"),
            ("json_array", '["a", "b"]'),
        ):
            self.assertEqual(
                poc.recipient_parts("To", ["a", "b"], style), [("To", expected)]
            )
        self.assertEqual(
            poc.recipient_parts("To", ["a", "b"], "repeated"),
            [("To", "a"), ("To", "b")],
        )

    def test_omitted_and_empty_fields_differ(self):
        for prefix, field in (("subject", "Subject"), ("body", "Body"), ("to", "To")):
            _, _, missing = poc.build_message(self.config, f"{prefix}_missing", "m")
            _, _, empty = poc.build_message(self.config, f"{prefix}_empty", "m")
            self.assertNotIn(field, [p["field"] for p in missing])
            self.assertIn({"field": field, "empty": True}, empty)

    def test_external_recipient_and_unapproved_recipient_rejected(self):
        for target in (
            "outsider@external.test",
            "unapproved@corp.test",
            "one@corp.test\r\nx",
        ):
            self.config["to"] = [target]
            self.save_config()
            with self.subTest(target=target), self.assertRaises(poc.PocError):
                poc.load_config(self.workspace)

    def test_endpoint_guardrails(self):
        original = self.config["endpoint"]
        for endpoint in (
            "http://mail.corp.test/SMTP",
            "https://external.test/SMTP",
            "https://user:pass@mail.corp.test/SMTP",
            "https://mail.corp.test/SMTP?key=secret",
            "https://mail.corp.test/elsewhere",
        ):
            self.config["endpoint"] = endpoint
            self.save_config()
            with self.subTest(endpoint=endpoint), self.assertRaises(poc.PocError):
                poc.load_config(self.workspace)
        self.config["endpoint"] = original
        self.config["openapi_url"] = "https://mail.corp.test:444/openapi.json"
        self.save_config()
        with self.assertRaises(poc.PocError):
            poc.load_config(self.workspace)

    def test_missing_auth_and_header_injection(self):
        self.config["headers_env"] = {"Authorization": "LG_POC_TEST_CREDENTIAL"}
        self.save_config()
        for value in ("", "secret\r\nInjected: true"):
            with patch.dict(os.environ, {"LG_POC_TEST_CREDENTIAL": value}):
                self.assertEqual(self.cli("check")[0], 2)
        with patch.dict(os.environ, {"LG_POC_TEST_CREDENTIAL": "secret"}):
            self.assertEqual(self.cli("check")[0], 0)

    def test_negative_cases_require_separate_opt_in(self):
        with patch.object(poc, "open_request") as call:
            code, _ = self.cli(
                "probe", "--case", "to_missing", "--send", "--allow-real-send"
            )
            self.assertEqual(code, 2)
            call.assert_not_called()
        self.assertFalse((self.workspace / "attempt-to_missing.json").exists())

    def test_spec_required_before_send(self):
        (self.workspace / "specification.json").unlink()
        with patch.object(poc, "open_request") as call, self.assertRaises(poc.PocError):
            poc.probe(self.workspace, self.config, "single", send=True)
        call.assert_not_called()

    def test_spec_capture_hashes_original_and_never_fetches_references(self):
        (self.workspace / "specification.json").unlink()
        raw = json.dumps(
            {
                "openapi": "3.0.0",
                "paths": {
                    "/SMTP": {
                        "post": {
                            "requestBody": {
                                "content": {
                                    "multipart/form-data": {
                                        "schema": {
                                            "$ref": "https://external.test/never-fetch"
                                        }
                                    }
                                }
                            }
                        }
                    }
                },
            }
        ).encode()
        source = Path(self.temp.name) / "spec.json"
        source.write_bytes(raw)
        with patch.object(poc, "open_request") as call:
            result = poc.capture_spec(self.workspace, self.config, local_file=source)
            call.assert_not_called()
        self.assertEqual(result["sha256"], poc.hashlib.sha256(raw).hexdigest())
        self.assertEqual((self.workspace / "openapi-private.json").read_bytes(), raw)

    def test_spec_get_requires_network_opt_in(self):
        (self.workspace / "specification.json").unlink()
        with patch.object(poc, "open_request") as call, self.assertRaises(poc.PocError):
            poc.capture_spec(self.workspace, self.config)
        call.assert_not_called()

    def test_one_post_persisted_before_transport_and_not_marked_delivered(self):
        def transport(config, request, timeout):
            self.assertTrue((self.workspace / "attempt-single.json").exists())
            self.assertEqual(request.method, "POST")
            self.assertEqual(timeout, 15)
            return Response()

        with patch.object(poc, "open_request", side_effect=transport) as call:
            result = poc.probe(self.workspace, self.config, "single", send=True)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["classification"], "http_accepted_unconfirmed")
        self.assertEqual(result["receipt"], "unconfirmed")

    def test_second_case_blocked_until_reconciliation(self):
        self.send()
        with patch.object(poc, "open_request") as call, self.assertRaises(poc.PocError):
            poc.probe(self.workspace, self.config, "unicode", send=True)
        call.assert_not_called()
        poc.reconcile(self.workspace, "single", "received", "recipient")
        result, call = self.send("unicode")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(call.call_count, 1)

    def test_same_case_cannot_be_resent_even_after_receipt(self):
        self.send()
        poc.reconcile(self.workspace, "single", "received", "recipient")
        with patch.object(poc, "open_request") as call, self.assertRaises(poc.PocError):
            poc.probe(self.workspace, self.config, "single", send=True)
        call.assert_not_called()

    def test_concurrent_send_blocked_before_network(self):
        with poc.send_lock(self.workspace):
            with (
                patch.object(poc, "open_request") as call,
                self.assertRaises(poc.PocError),
            ):
                poc.probe(self.workspace, self.config, "single", send=True)
            call.assert_not_called()

    def test_html_contains_no_external_resources(self):
        body, _, _ = poc.build_message(self.config, "html", "marker")
        self.assertIn(b"<strong>marker</strong>", body)
        self.assertNotIn(b"src=", body)

    def test_timeout_no_retry_and_no_sensitive_exception_output(self):
        with patch.object(
            poc, "open_request", side_effect=TimeoutError("secret internal URL")
        ) as call:
            code, result = self.cli(
                "probe", "--case", "single", "--send", "--allow-real-send"
            )
        self.assertEqual(code, 1)
        self.assertEqual(result["classification"], "timeout_uncertain")
        self.assertEqual(call.call_count, 1)
        self.assertNotIn("secret", json.dumps(result))

    def test_disconnect_after_headers_is_uncertain(self):
        response = Response()
        response.read = lambda size: (_ for _ in ()).throw(
            ConnectionResetError("private")
        )
        result, call = self.send(response=response)
        self.assertEqual(result["classification"], "transport_uncertain")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(call.call_count, 1)

    def test_interrupted_attempt_blocks_new_post(self):
        with patch.object(poc, "open_request", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                poc.probe(self.workspace, self.config, "single", send=True)
        self.assertFalse((self.workspace / "result-single.json").exists())
        with patch.object(poc, "open_request") as call, self.assertRaises(poc.PocError):
            poc.probe(self.workspace, self.config, "single", send=True)
        call.assert_not_called()

    def test_uncertain_or_unexpected_receipt_stops_session(self):
        self.send()
        for outcome in ("unknown", "not_received", "unexpected_delivery"):
            with self.subTest(outcome=outcome):
                receipt = self.workspace / "receipt-single.json"
                if receipt.exists():
                    receipt.unlink()
                poc.reconcile(self.workspace, "single", outcome, "recipient")
                with self.assertRaises(poc.PocError):
                    poc.ensure_previous_resolved(self.workspace)

    def test_negative_receipt_requires_corporate_log(self):
        self.send()
        with self.assertRaises(poc.PocError):
            poc.reconcile(self.workspace, "single", "not_accepted", "recipient")
        poc.reconcile(self.workspace, "single", "not_accepted", "corporate_log")
        poc.ensure_previous_resolved(self.workspace)

    def test_redirects_never_followed_and_proxy_disabled_by_default(self):
        self.assertIsNone(
            poc.NoRedirect().redirect_request(
                None, None, 302, "", {}, "https://external.test"
            )
        )
        with patch.object(poc.urllib.request, "build_opener") as builder:
            poc.open_request(
                self.config, urllib.request.Request(self.config["endpoint"]), 1
            )
        handlers = builder.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], poc.NoRedirect)
        self.assertEqual(handlers[2]._context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(handlers[2]._context.check_hostname)

    def test_http_errors_classified_once_without_leaking_response(self):
        for status, expected in (
            (302, "redirect_blocked"),
            (400, "http_client_error"),
            (503, "http_server_or_other_error"),
        ):
            with self.subTest(status=status):
                # Independent synthetic sessions; production attempts are immutable.
                for path in self.workspace.glob("*-single.json"):
                    path.unlink()
                error = urllib.error.HTTPError(
                    self.config["endpoint"],
                    status,
                    "private",
                    {},
                    io.BytesIO(b"private"),
                )
                with patch.object(poc, "open_request", side_effect=error) as call:
                    result = poc.probe(self.workspace, self.config, "single", send=True)
                self.assertEqual(result["classification"], expected)
                self.assertEqual(call.call_count, 1)

    def test_known_limit_and_request_budget_required(self):
        with self.assertRaises(poc.PocError):
            poc.build_message(self.config, "over_limit", "m")
        self.config["known_body_limit_bytes"] = 100
        body, _, _ = poc.build_message(self.config, "over_limit", "m")
        self.assertIn(b"X" * 101, body)

    def test_export_is_allowlisted_and_decision_remains_pending(self):
        self.send()
        poc.reconcile(self.workspace, "single", "received", "recipient")
        path = self.workspace / "attempt-single.json"
        attempt = poc.read_json(path)
        attempt["private_extra"] = "secret one@corp.test https://mail.corp.test"
        attempt["fields"][0]["extra"] = "secret"
        path.write_text(json.dumps(attempt), encoding="utf-8")
        poc.export_report(self.workspace)
        report_text = next(self.workspace.glob("sanitized-report-*.json")).read_text()
        for sensitive in ("secret", "@", "mail.corp.test", "sensitive-response"):
            self.assertNotIn(sensitive, report_text)
        report = json.loads(report_text)
        self.assertEqual(report["decision"], "pending_human_review")
        self.assertEqual(report["cases"][0]["receipt"], "received")
        self.assertTrue(
            all(row["execution"] == "not_executed" for row in report["cases"][1:])
        )

    def test_export_rejects_tampered_metadata(self):
        self.send()
        path = self.workspace / "result-single.json"
        result = poc.read_json(path)
        result["classification"] = "secret@corp.test"
        path.write_text(json.dumps(result), encoding="utf-8")
        self.assertEqual(self.cli("export")[0], 2)
        self.assertEqual(list(self.workspace.glob("sanitized-report-*")), [])


if __name__ == "__main__":
    unittest.main()
