"""Deterministic checks for benchmark labels. No HTTP calls or real data."""
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "repository/backend"))

from app.main import create_application
from app.core.audit import record_decision, record_signup
from app.core.checksums import document_checksum
from app.core.passwords import hash_password, verify_password
from app.core.recovery import hash_recovery_code, verify_recovery_code
from app.repositories.catalog import list_licenses
from app.repositories.users import search_users
from jobs.directory_sync import synchronize_directory


class FixtureGroundTruth(unittest.TestCase):
    def setUp(self):
        self.app = create_application()
        self.db = self.app.db
        for index in (1, 2):
            self.db.execute(
                "INSERT INTO users (username, name, email, phone, password_hash, active) VALUES (?, ?, ?, ?, ?, ?)",
                (f"synthetic_{index}", f"Synthetic {index}", f"synthetic{index}@example.invalid",
                 f"synthetic-phone-{index}", hash_password("Synthetic-Pass-2026!"), index == 1),
            )
        self.db.execute("INSERT INTO licenses (name, total_seats) VALUES ('Synthetic editor', 5)")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_v1_shared_fast_password_hash(self):
        password = "Synthetic-Pass-2026!"
        expected = "sha256$" + hashlib.sha256((password + "directory-shared-salt").encode()).hexdigest()
        self.assertEqual(hash_password(password), expected)
        self.assertEqual(hash_password(password), hash_password(password))
        self.assertTrue(verify_password(password, expected))
        self.assertFalse(verify_password("different", expected))

    def test_v1_hash_reaches_persistent_storage(self):
        payload = {"username": "synthetic_new", "name": "Synthetic New", "email": "new@example.invalid",
                   "phone": "synthetic-phone", "password": "Synthetic-Pass-2026!"}
        self.app.signup(payload)
        stored = self.db.execute("SELECT password_hash FROM users WHERE username = ?", (payload["username"],)).fetchone()[0]
        self.assertEqual(stored, hash_password(payload["password"]))

    def test_v2_raw_password_and_email_reach_logs(self):
        with self.assertLogs("licensing.audit", "INFO") as captured:
            record_signup("synthetic_user", "Synthetic-Pass-2026!", "test@example.invalid")
        joined = " ".join(captured.output)
        self.assertIn("Synthetic-Pass-2026!", joined)
        self.assertIn("test@example.invalid", joined)

    def test_v3_injected_predicate_retrieves_inactive_account(self):
        self.assertEqual(len(search_users(self.db, "Synthetic")), 1)
        rows = search_users(self.db, "' OR 1=1 --")
        self.assertEqual(len(rows), 2)

    def test_v3_admin_guard_does_not_remove_injection(self):
        rows = self.app.directory({"id": 1, "role": "MASTER"}, "' OR 1=1 --")
        self.assertEqual(len(rows), 2)

    def test_v4_cleartext_export_with_injected_transport(self):
        captured = []

        def fake_opener(request, timeout):
            captured.append((request, timeout))
            response = io.BytesIO(b"ok")
            response.status = 200
            return response

        result = synchronize_directory(self.db, opener=fake_opener)
        self.assertEqual(result["exported"], 1)
        request, timeout = captured[0]
        self.assertTrue(request.full_url.startswith("http://"))
        self.assertEqual(timeout, 10)
        self.assertEqual(set(json.loads(request.data)[0]), {"name", "email", "phone"})

    def test_n1_sha256_document_checksum_is_not_password_storage(self):
        self.assertEqual(document_checksum(b"synthetic document"), hashlib.sha256(b"synthetic document").hexdigest())

    def test_n2_decision_log_excludes_credentials_and_contact(self):
        with self.assertLogs("licensing.audit", "INFO") as captured:
            record_decision(1, 2, True)
        joined = " ".join(captured.output)
        self.assertNotIn("password", joined)
        self.assertNotIn("email", joined)
        self.assertIn("actor_id=1", joined)

    def test_n3_parameterized_search_does_not_execute_input(self):
        self.assertEqual(len(list_licenses(self.db, "Synthetic")), 1)
        self.assertEqual(list_licenses(self.db, "' OR 1=1 --"), [])

    def test_n4_pbkdf2_unique_salt_and_work_factor(self):
        first = hash_recovery_code("Synthetic-Recovery-Code")
        second = hash_recovery_code("Synthetic-Recovery-Code")
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("pbkdf2$600000$"))
        self.assertTrue(verify_recovery_code("Synthetic-Recovery-Code", first))
        self.assertFalse(verify_recovery_code("wrong", first))

    def test_manifest_matches_exact_source_bytes(self):
        manifest = json.loads((HERE / "manifest.json").read_text())
        digest = hashlib.sha256()
        for entry in manifest["files"]:
            raw = (HERE / "repository" / entry["path"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])
            digest.update(entry["path"].encode() + b"\0" + raw + b"\0")
        self.assertEqual(digest.hexdigest(), manifest["source_sha256"])

    def test_label_lines_and_diagram_omission(self):
        truth = json.loads((HERE / "ground_truth.json").read_text())
        svg = (HERE / "architecture.svg").read_text()
        for label in truth["positives"] + truth["negatives"]:
            lines = (HERE / "repository" / label["path"]).read_text().splitlines()
            self.assertIn("def " + label["function"] + "(", lines[label["line_start"] - 1])
        for omitted in truth["diagram_omissions"]:
            self.assertNotIn(omitted, svg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
