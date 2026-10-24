"""End-to-end and unit tests. Run: python3 -m unittest discover -s tests -v"""
import contextlib
import copy
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "safe-unsubscribe")
sys.path.insert(0, os.path.join(SKILL, "scripts"))

import build_plan  # noqa: E402
import common  # noqa: E402
import execute_plan  # noqa: E402
import parse_headers  # noqa: E402
import scan_mailbox  # noqa: E402
import validate_plan  # noqa: E402
import verify_results  # noqa: E402

FIXTURE = os.path.join(SKILL, "evals", "fixtures", "mailbox.json")
NOW = "2026-10-25T12:00:00Z"


class Workspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        with contextlib.redirect_stdout(io.StringIO()):
            scan_mailbox.main(["--source", FIXTURE, "--out-dir", self.dir, "--now", NOW])
        self.scan_path = os.path.join(self.dir, "candidates.json")
        self.targets_path = os.path.join(self.dir, "targets.private.json")
        self.scan = common.read_json(self.scan_path)
        self.by_addr = {c["sender_address"]: c for c in self.scan["candidates"]}

    def plan(self, **kw):
        kw.setdefault("recommended", True)
        return build_plan.build_plan(self.scan, common.sha256_file(self.scan_path), **kw)

    def errors(self, plan, **kw):
        return validate_plan.validate(plan, self.scan, common.sha256_file(self.scan_path), **kw)

    def run_exec(self, plan, **kw):
        scan = dict(self.scan, _sha=common.sha256_file(self.scan_path))
        targets = common.read_json(self.targets_path)["targets"]
        return execute_plan.execute(plan, scan, targets, **kw)


class ScanTests(Workspace):
    def test_recommendations(self):
        a = self.by_addr
        self.assertEqual(a["deals@shopping.example"]["recommended_action"], "unsubscribe")
        self.assertEqual(a["deals@shopping.example"]["method"], "rfc8058-post")
        self.assertEqual(a["fares@airline.example"]["recommended_action"], "keep")
        self.assertEqual(a["list@localclub.example"]["recommended_action"], "keep")
        self.assertEqual(a["list@localclub.example"]["method"], "mailto")
        self.assertEqual(a["promo@gadgets.example"]["method"], "preference-page")
        self.assertEqual(a["blast@nounsub.example"]["recommended_action"], "create_rule")

    def test_suspicious_never_uses_link(self):
        for addr in ("win@unknown-offers.example", "hello@oddsender.example", "help@random-mail.example"):
            c = self.by_addr[addr]
            self.assertEqual(c["recommended_action"], "block_or_report", addr)
            self.assertEqual(c["method"], "unsafe", addr)

    def test_transactional_and_security_excluded(self):
        for addr in ("receipts@store.example", "alerts@bank.example"):
            c = self.by_addr[addr]
            self.assertEqual(c["recommended_action"], "keep", addr)
            self.assertTrue(c["excluded_reasons"], addr)

    def test_old_messages_outside_window_ignored(self):
        self.assertNotIn("old@ancient.example", self.by_addr)

    def test_same_publisher_grouped_by_key(self):
        self.assertEqual(self.by_addr["news@pub.example"]["group_key"],
                         self.by_addr["offers@mail.pub.example"]["group_key"])

    def test_candidates_file_has_no_urls(self):
        with open(self.scan_path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("mailto:", text)

    def test_targets_file_private(self):
        self.assertEqual(os.stat(self.targets_path).st_mode & 0o777, 0o600)

    def test_schema_valid(self):
        self.assertEqual(common.validate_schema(self.scan, common.load_schema("candidate.schema.json")), [])


class PlanValidationTests(Workspace):
    def test_recommended_plan_is_valid_and_excludes_keeps(self):
        plan = self.plan()
        self.assertEqual(self.errors(plan), [])
        ids = {a["candidate_id"] for a in plan["actions"]}
        self.assertNotIn(self.by_addr["fares@airline.example"]["candidate_id"], ids)
        self.assertNotIn(self.by_addr["alerts@bank.example"]["candidate_id"], ids)

    def test_keep_exception_by_domain(self):
        plan = self.plan(keep=["pub.example"])
        ids = {a["candidate_id"] for a in plan["actions"]}
        self.assertNotIn(self.by_addr["news@pub.example"]["candidate_id"], ids)
        self.assertNotIn(self.by_addr["offers@mail.pub.example"]["candidate_id"], ids)
        self.assertIn(self.by_addr["deals@shopping.example"]["candidate_id"], ids)

    def test_plan_not_approved_by_default(self):
        plan = self.plan()
        self.assertFalse(plan["approved"])
        self.assertTrue(any("not approved" in e for e in self.errors(plan, require_approved=True)))

    def test_rejects_transactional(self):
        plan = self.plan(recommended=False, only=["receipts@store.example"])
        self.assertTrue(any("never bulk-actioned" in e for e in self.errors(plan)))

    def test_rejects_unsubscribe_on_suspicious(self):
        cid = self.by_addr["win@unknown-offers.example"]["candidate_id"]
        plan = self.plan(recommended=False, only=["win@unknown-offers.example"])
        plan["actions"][0]["action"] = "unsubscribe"
        self.assertTrue(any("high-risk" in e for e in self.errors(plan)), cid)

    def test_rejects_unknown_id_and_extra_properties(self):
        plan = self.plan()
        bad = copy.deepcopy(plan)
        bad["actions"][0]["candidate_id"] = "c_000000000000"
        self.assertTrue(any("unknown candidate_id" in e for e in self.errors(bad)))
        bad = copy.deepcopy(plan)
        bad["actions"][0]["url"] = "https://evil.example/x"
        self.assertTrue(any("unexpected property 'url'" in e for e in self.errors(bad)))

    def test_rejects_method_tampering(self):
        plan = self.plan(recommended=False, only=["promo@gadgets.example"])
        plan["actions"][0]["method"] = "rfc8058-post"
        self.assertTrue(any("differs from scanned method" in e for e in self.errors(plan)))

    def test_rejects_edited_locked_fields(self):
        plan = self.plan()
        cand = self.by_addr["win@unknown-offers.example"]
        cand["risk"], cand["method"] = "low", "rfc8058-post"
        self.assertTrue(any("script-derived" in e for e in self.errors(plan)))

    def test_allows_editing_reason_and_downgrading_action(self):
        self.by_addr["deals@shopping.example"].update(recommended_action="keep", reason="user prefers to keep")
        plan = self.plan()
        self.assertEqual(self.errors(plan), [])

    def test_rejects_stale_scan(self):
        plan = self.plan()
        plan["scan_sha256"] = "0" * 64
        self.assertTrue(any("different scan" in e for e in self.errors(plan)))


class ExecutorTests(Workspace):
    def approved(self, **kw):
        plan = self.plan(**kw)
        plan["approved"], plan["approved_at"] = True, datetime.now(timezone.utc).isoformat()
        return plan

    def test_refuses_unapproved(self):
        with self.assertRaises(ValueError):
            self.run_exec(self.plan())

    def test_dry_run_makes_no_calls(self):
        def boom(url):
            raise AssertionError("network used in dry run")
        results = execute_plan.execute(self.approved(), dict(self.scan, _sha=common.sha256_file(self.scan_path)),
                                       common.read_json(self.targets_path)["targets"], poster=boom)
        self.assertTrue(all(r["status"] in ("dry_run", "recommendation_only") for r in results))

    def test_only_planned_unsubscribes_are_posted(self):
        posted = []
        results = self.run_exec(self.approved(keep=["pub.example"]), execute_real=True,
                                poster=lambda url: (posted.append(url), (200, False))[1], opener=lambda u: None)
        self.assertEqual(len(posted), 1)  # shopping.example only; gadgets is a hand-off
        self.assertTrue(posted[0].startswith("https://mail.shopping.example/"))
        by = {r["sender_address"]: r for r in results}
        self.assertEqual(by["deals@shopping.example"]["status"], "succeeded")
        self.assertEqual(by["promo@gadgets.example"]["status"], "handoff")
        self.assertEqual(by["win@unknown-offers.example"]["status"], "recommendation_only")
        self.assertEqual(by["blast@nounsub.example"]["status"], "pending_host")

    def test_partial_failure_does_not_stop_batch(self):
        def flaky(url):
            if "shopping" in url:
                raise OSError("connection reset")
            return 202, False
        results = self.run_exec(self.approved(), execute_real=True, poster=flaky, opener=lambda u: None)
        by = {r["sender_address"]: r for r in results}
        self.assertEqual(by["deals@shopping.example"]["status"], "failed")
        self.assertEqual(by["news@pub.example"]["status"], "succeeded")

    def test_redirect_response_is_failure(self):
        results = self.run_exec(self.approved(recommended=False, only=["deals@shopping.example"]),
                                execute_real=True, poster=lambda u: (302, True))
        self.assertEqual(results[0]["status"], "failed")

    def test_mailto_preview_requires_no_sending(self):
        plan = self.approved(recommended=False, only=["list@localclub.example"])
        results = self.run_exec(plan, execute_real=True)
        self.assertEqual(results[0]["status"], "pending_host")
        self.assertEqual(results[0]["mailto_preview"]["to"], "list-leave@localclub.example")

    def test_results_do_not_leak_tokens(self):
        results = self.run_exec(self.approved(), execute_real=True, poster=lambda u: (200, False), opener=lambda u: None)
        text = str(results)
        for token in ("8f3a9c1d2b7e4f60", "f00dfeed12345678", "user=42"):
            self.assertNotIn(token, text)

    def test_tampered_target_rejected(self):
        scan = dict(self.scan, _sha=common.sha256_file(self.scan_path))
        targets = copy.deepcopy(common.read_json(self.targets_path)["targets"])
        cid = self.by_addr["deals@shopping.example"]["candidate_id"]
        targets[cid]["sender_address"] = "someone@else.example"
        results = execute_plan.execute(self.approved(recommended=False, only=["deals@shopping.example"]),
                                       scan, targets, execute_real=True, poster=lambda u: (200, False))
        self.assertEqual(results[0]["status"], "failed")


class VerifyTests(Workspace):
    def test_verify_statuses(self):
        doc = {"dry_run": False, "results": [
            {"sender_address": "deals@shopping.example", "method": "rfc8058-post", "action": "unsubscribe",
             "status": "succeeded", "executed_at": "2026-08-01T00:00:00+00:00"},
            {"sender_address": "news@pub.example", "method": "rfc8058-post", "action": "unsubscribe",
             "status": "succeeded", "executed_at": "2026-10-24T00:00:00+00:00"},
            {"sender_address": "blast@nounsub.example", "method": "none", "action": "create_rule",
             "status": "pending_host", "executed_at": "2026-08-01T00:00:00+00:00"},
        ]}
        rows = {r["sender_address"]: r["status"] for r in verify_results.verify(doc, self.scan)}
        self.assertEqual(rows["deals@shopping.example"], "still_mailing")
        self.assertEqual(rows["news@pub.example"], "stopped")
        self.assertEqual(rows["blast@nounsub.example"], "not_applicable")


class UrlAndHeaderTests(unittest.TestCase):
    def test_https_url_rules(self):
        good = "https://mail.example.com/u/abc"
        self.assertTrue(common.check_https_url(good)[0])
        for bad in ("http://example.com/u", "https://127.0.0.1/u", "https://localhost/u", "https://user:pw@example.com/u",
                    "https://example.com:8443/u", "https://intranet/u", "javascript:alert(1)", "https://exa mple.com/",
                    "https://printer.local/u", "https://xn--e1afmkfd.example/u"):
            self.assertFalse(common.check_https_url(bad)[0], bad)

    def test_mailto_rules(self):
        ok, _ = common.parse_mailto("mailto:leave@list.example?subject=unsubscribe%20me")
        self.assertEqual(ok["subject"], "unsubscribe me")
        for bad in ("mailto:a@x.example,b@y.example", "mailto:a@x.example?cc=b@y.example", "mailto:not-an-address",
                    "mailto:a@x.example?subject=hi%0ABcc:evil@x.example"):
            self.assertIsNone(common.parse_mailto(bad)[0], bad)

    def test_one_click_needs_post_header_and_auth(self):
        base = {"from": "A <a@x.example>", "list-unsubscribe": "<https://x.example/u/1>",
                "authentication-results": "mx; dkim=pass; spf=pass; dmarc=pass"}
        self.assertEqual(parse_headers.analyze(base)["method"], "preference-page")
        self.assertEqual(parse_headers.analyze({**base, "list-unsubscribe-post": "List-Unsubscribe=One-Click"})["method"],
                         "rfc8058-post")
        noauth = {k: v for k, v in base.items() if k != "authentication-results"}
        self.assertEqual(parse_headers.analyze({**noauth, "list-unsubscribe-post": "List-Unsubscribe=One-Click"})["method"],
                         "preference-page")

    def test_gmail_and_graph_records(self):
        gmail = {"internalDate": "1792929600000", "labelIds": ["INBOX", "UNREAD"], "payload": {"headers": [
            {"name": "From", "value": "A <a@x.example>"}, {"name": "Subject", "value": "Hi"}]}}
        headers, read, fallback = parse_headers.normalize_record(gmail)
        self.assertEqual((headers["from"], read), ("A <a@x.example>", False))
        self.assertTrue(fallback)
        graph = {"subject": "Hi", "isRead": True, "receivedDateTime": "2026-10-01T00:00:00Z",
                 "internetMessageHeaders": [{"name": "From", "value": "A <a@x.example>"}]}
        headers, read, _ = parse_headers.normalize_record(graph)
        self.assertEqual((headers["subject"], read), ("Hi", True))

    def test_redaction(self):
        self.assertNotIn("abcdef123456", common.redact_url("https://x.example/u/abcdef123456?t=secret"))
        self.assertNotIn("secret", common.redact_url("https://x.example/u?t=secret"))


if __name__ == "__main__":
    unittest.main()
