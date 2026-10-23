#!/usr/bin/env python3
"""Build the synthetic, local-only architecture benchmark; no real project data."""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
from pathlib import Path
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "tests/fixtures/architecture_benchmark"

SOURCES = {
    "backend/app/main.py": '''
        from app.api.routes import Routes
        from app.db.session import connect, initialize


        def create_application(database=":memory:"):
            connection = connect(database)
            initialize(connection)
            return Routes(connection)
    ''',
    "backend/app/api/routes.py": '''
        from app.core.errors import AccessDenied
        from app.schemas.dto import Signup, SearchQuery
        from app.services.accounts import register, authenticate
        from app.services.requests import create_request, decide_request
        from app.repositories.users import search_users
        from app.repositories.catalog import list_licenses
        from app.services.dashboard import summary


        class Routes:
            def __init__(self, db):
                self.db = db

            def signup(self, body):
                payload = Signup.from_mapping(body)
                return register(self.db, payload)

            def login(self, body):
                return authenticate(self.db, body["username"], body["password"])

            def directory(self, actor, query):
                if not actor or actor["role"] != "MASTER":
                    raise AccessDenied("Directory is restricted to administrators")
                return search_users(self.db, SearchQuery(query).text)

            def licenses(self, actor, query=""):
                if not actor:
                    raise AccessDenied("Sign in first")
                return list_licenses(self.db, SearchQuery(query).text)

            def request_license(self, actor, license_id, reason):
                if not actor:
                    raise AccessDenied("Sign in first")
                return create_request(self.db, actor, license_id, reason)

            def decide(self, actor, request_id, approved):
                if not actor or actor["role"] != "MASTER":
                    raise AccessDenied("Only administrators may decide requests")
                return decide_request(self.db, actor, request_id, approved)

            def dashboard(self, actor):
                if not actor:
                    raise AccessDenied("Sign in first")
                return summary(self.db, actor["id"])
    ''',
    "backend/app/core/passwords.py": '''
        import hashlib
        import hmac


        def hash_password(password: str) -> str:
            salt = "directory-shared-salt"
            digest = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
            return "sha256$" + digest


        def verify_password(password: str, stored: str) -> bool:
            return hmac.compare_digest(hash_password(password), stored)
    ''',
    "backend/app/core/audit.py": '''
        import logging

        log = logging.getLogger("licensing.audit")


        def record_signup(username: str, password: str, email: str):
            log.info("signup username=%s password=%s email=%s", username, password, email)


        def record_decision(actor_id: int, request_id: int, approved: bool):
            log.info("decision actor_id=%d request_id=%d approved=%s", actor_id, request_id, approved)
    ''',
    "backend/app/core/errors.py": '''
        class AccessDenied(Exception):
            pass


        class InvalidInput(Exception):
            pass


        class Conflict(Exception):
            pass
    ''',
    "backend/app/core/checksums.py": '''
        import hashlib


        def document_checksum(content: bytes) -> str:
            return hashlib.sha256(content).hexdigest()


        def same_document(content: bytes, expected_checksum: str) -> bool:
            return document_checksum(content) == expected_checksum
    ''',
    "backend/app/core/recovery.py": '''
        import hashlib
        import hmac
        import secrets

        ITERATIONS = 600_000


        def hash_recovery_code(raw: str) -> str:
            salt = secrets.token_bytes(16)
            digest = hashlib.pbkdf2_hmac("sha256", raw.encode(), salt, ITERATIONS)
            return f"pbkdf2${ITERATIONS}${salt.hex()}${digest.hex()}"


        def verify_recovery_code(raw: str, encoded: str) -> bool:
            try:
                algorithm, iterations, salt_hex, expected_hex = encoded.split("$")
                if algorithm != "pbkdf2" or not 600_000 <= int(iterations) <= 1_000_000:
                    return False
                salt = bytes.fromhex(salt_hex)
                if len(salt) != 16:
                    return False
                actual = hashlib.pbkdf2_hmac("sha256", raw.encode(), salt, int(iterations))
                return hmac.compare_digest(actual, bytes.fromhex(expected_hex))
            except (ValueError, TypeError):
                return False
    ''',
    "backend/app/db/session.py": '''
        import sqlite3


        def connect(path=":memory:"):
            db = sqlite3.connect(path)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            return db


        def initialize(db):
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL,
                    password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'USER',
                    active INTEGER NOT NULL DEFAULT 1,
                    CHECK (role IN ('USER', 'MASTER'))
                );
                CREATE TABLE IF NOT EXISTS licenses (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    total_seats INTEGER NOT NULL CHECK(total_seats >= 0),
                    active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                    license_id INTEGER NOT NULL REFERENCES licenses(id),
                    reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'PENDING',
                    processed_by INTEGER REFERENCES users(id),
                    CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELED'))
                );
                CREATE TABLE IF NOT EXISTS assignments (
                    id INTEGER PRIMARY KEY, request_id INTEGER UNIQUE NOT NULL REFERENCES requests(id),
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    license_id INTEGER NOT NULL REFERENCES licenses(id),
                    active INTEGER NOT NULL DEFAULT 1
                );
            """)
    ''',
    "backend/app/schemas/dto.py": '''
        from dataclasses import dataclass
        from app.core.errors import InvalidInput


        @dataclass(frozen=True)
        class Signup:
            username: str
            name: str
            email: str
            phone: str
            password: str

            @classmethod
            def from_mapping(cls, data):
                keys = ("username", "name", "email", "phone", "password")
                if any(not isinstance(data.get(key), str) for key in keys):
                    raise InvalidInput("All signup fields must be strings")
                if not 3 <= len(data["username"]) <= 40:
                    raise InvalidInput("Username length must be between 3 and 40")
                if not 12 <= len(data["password"]) <= 128:
                    raise InvalidInput("Password length must be between 12 and 128")
                if "@" not in data["email"] or len(data["email"]) > 254:
                    raise InvalidInput("Invalid email")
                if not 1 <= len(data["name"]) <= 80 or len(data["phone"]) > 30:
                    raise InvalidInput("Invalid contact information")
                return cls(**{key: data[key] for key in keys})


        @dataclass(frozen=True)
        class SearchQuery:
            text: str

            def __post_init__(self):
                if not isinstance(self.text, str) or len(self.text) > 150:
                    raise InvalidInput("Search query must be at most 150 characters")
    ''',
    "backend/app/repositories/users.py": '''
        def find_by_username(db, username):
            return db.execute("SELECT * FROM users WHERE username = ? AND active = 1", (username,)).fetchone()


        def create_user(db, payload, password_hash):
            cursor = db.execute(
                "INSERT INTO users (username, name, email, phone, password_hash) VALUES (?, ?, ?, ?, ?)",
                (payload.username, payload.name, payload.email, payload.phone, password_hash),
            )
            return cursor.lastrowid


        def search_users(db, query):
            statement = f"SELECT id, username, name, email FROM users WHERE active = 1 AND name LIKE '%{query}%'"
            return [dict(row) for row in db.execute(statement).fetchall()]


        def public_profile(row):
            return {key: row[key] for key in ("id", "username", "name", "role")}
    ''',
    "backend/app/repositories/catalog.py": '''
        def list_licenses(db, query):
            rows = db.execute(
                "SELECT id, name, total_seats FROM licenses WHERE active = 1 AND name LIKE ? ORDER BY name",
                ("%" + query + "%",),
            ).fetchall()
            return [dict(row) for row in rows]


        def license_by_id(db, license_id):
            row = db.execute("SELECT * FROM licenses WHERE id = ? AND active = 1", (license_id,)).fetchone()
            return dict(row) if row else None


        def occupied_seats(db, license_id):
            return db.execute(
                "SELECT COUNT(*) FROM assignments WHERE license_id = ? AND active = 1", (license_id,)
            ).fetchone()[0]
    ''',
    "backend/app/services/accounts.py": '''
        from app.core.errors import AccessDenied, Conflict
        from app.core.passwords import hash_password, verify_password
        from app.core.audit import record_signup
        from app.repositories.users import find_by_username, create_user, public_profile


        def register(db, payload):
            if find_by_username(db, payload.username):
                raise Conflict("Username is already registered")
            password_hash = hash_password(payload.password)
            with db:
                user_id = create_user(db, payload, password_hash)
            record_signup(payload.username, payload.password, payload.email)
            return {"id": user_id, "username": payload.username}


        def authenticate(db, username, password):
            row = find_by_username(db, username)
            if not row or not verify_password(password, row["password_hash"]):
                raise AccessDenied("Incorrect credentials")
            return public_profile(row)
    ''',
    "backend/app/services/requests.py": '''
        from app.core.errors import AccessDenied, Conflict, InvalidInput
        from app.core.audit import record_decision
        from app.repositories.catalog import license_by_id, occupied_seats


        def create_request(db, actor, license_id, reason):
            if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
                raise InvalidInput("A short reason is required")
            if not license_by_id(db, license_id):
                raise InvalidInput("Unknown license")
            existing = db.execute(
                "SELECT id FROM requests WHERE user_id = ? AND license_id = ? AND status = 'PENDING'",
                (actor["id"], license_id),
            ).fetchone()
            if existing:
                raise Conflict("A request is already pending")
            with db:
                cursor = db.execute(
                    "INSERT INTO requests (user_id, license_id, reason) VALUES (?, ?, ?)",
                    (actor["id"], license_id, reason),
                )
            return {"id": cursor.lastrowid, "status": "PENDING"}


        def decide_request(db, actor, request_id, approved):
            if actor["role"] != "MASTER":
                raise AccessDenied("Only administrators may decide requests")
            row = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
            if not row or row["status"] != "PENDING":
                raise Conflict("Request is not pending")
            license = license_by_id(db, row["license_id"])
            if approved and (not license or occupied_seats(db, license["id"]) >= license["total_seats"]):
                raise Conflict("No seats available")
            status = "APPROVED" if approved else "REJECTED"
            with db:
                db.execute(
                    "UPDATE requests SET status = ?, processed_by = ? WHERE id = ?",
                    (status, actor["id"], request_id),
                )
                if approved:
                    db.execute(
                        "INSERT INTO assignments (request_id, user_id, license_id) VALUES (?, ?, ?)",
                        (request_id, row["user_id"], row["license_id"]),
                    )
            record_decision(actor["id"], request_id, approved)
            return {"id": request_id, "status": status}
    ''',
    "backend/app/services/dashboard.py": '''
        def summary(db, user_id):
            requests = db.execute(
                "SELECT status, COUNT(*) AS count FROM requests WHERE user_id = ? GROUP BY status",
                (user_id,),
            ).fetchall()
            active = db.execute(
                "SELECT COUNT(*) FROM assignments WHERE user_id = ? AND active = 1", (user_id,)
            ).fetchone()[0]
            return {
                "requests": {row["status"]: row["count"] for row in requests},
                "active_assignments": active,
            }
    ''',
    "backend/jobs/directory_sync.py": '''
        import json
        import urllib.request

        DESTINATION = "http://directory-partner.example.invalid/import"


        def synchronize_directory(db, opener=urllib.request.urlopen):
            rows = db.execute("SELECT name, email, phone FROM users WHERE active = 1").fetchall()
            payload = json.dumps([dict(row) for row in rows]).encode("utf-8")
            request = urllib.request.Request(
                DESTINATION, data=payload, headers={"Content-Type": "application/json"}, method="POST"
            )
            with opener(request, timeout=10) as response:
                return {"status": response.status, "exported": len(rows)}
    ''',
}


def span(source, function):
    tree = ast.parse(source)
    node = next(node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function)
    return {"line_start": node.lineno, "line_end": node.end_lineno}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def diagram():
    def box(x, y, width, height, title, lines, fill="#f1f6ff"):
        result = f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="{fill}" stroke="#57799a" stroke-width="2"/>'
        result += f'<text x="{x+16}" y="{y+29}" font-size="21" font-weight="700">{html.escape(title)}</text>'
        for index, line in enumerate(lines):
            result += f'<text x="{x+16}" y="{y+55+index*22}" font-size="15">{html.escape(line)}</text>'
        return result

    def arrow(x1, y1, x2, y2, label=""):
        result = f'<path d="M{x1},{y1} L{x2},{y2}" fill="none" stroke="#476988" stroke-width="2" marker-end="url(#arrow)"/>'
        if label:
            result += f'<text x="{(x1+x2)/2+8}" y="{(y1+y2)/2-8}" font-size="15">{html.escape(label)}</text>'
        return result

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1040" viewBox="0 0 1400 1040"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10" fill="#476988"/></marker></defs><rect width="1400" height="1040" fill="white"/><g font-family="Arial,sans-serif" fill="#21364b">',
             '<text x="35" y="42" font-size="27" font-weight="700">Synthetic Lichu-like licensing portal: web application view v1</text>',
             '<text x="35" y="73" font-size="17">Paths are relative to repository root. This view documents the web application, not all deployed workloads.</text>',
             '<rect x="25" y="235" width="1350" height="680" rx="14" fill="#fafcff" stroke="#94a7ba" stroke-dasharray="8 6"/>',
             '<text x="43" y="263" font-size="16">Application trust boundary</text>',
             box(500,100,400,90,"Employee / administrator browser",["Account and license operations"],"#f0f8f1"),
             box(490,290,420,126,"API / session-authorized routes",["backend/app/api/routes.py", "backend/app/schemas/dto.py", "backend/app/main.py"]),
             box(45,470,425,150,"Account registration / login",["backend/app/services/accounts.py", "backend/app/core/passwords.py", "backend/app/core/recovery.py", "Employee contact + credentials"]),
             box(490,470,420,150,"License request / approval",["backend/app/services/requests.py", "backend/app/services/dashboard.py", "backend/app/repositories/catalog.py", "Seat allocation + request state"]),
             box(955,470,385,150,"Audit / document utilities",["backend/app/core/audit.py", "backend/app/core/checksums.py", "Registration and decision events"]),
             box(130,740,450,105,"Employee directory repository",["backend/app/repositories/users.py", "Account lookup + directory search"]),
             box(690,740,480,105,"Database session / tables",["backend/app/db/session.py", "users, licenses, requests, assignments"]),
             box(440,940,530,75,"Persistent database",["Employee contact, password hashes, license state"],"#f0f8f1"),
             arrow(700,190,700,290,"HTTPS"), arrow(490,355,255,470), arrow(700,416,700,470), arrow(910,355,1145,470),
             arrow(255,620,355,740,"read / write"), arrow(700,620,930,740,"SQL"), arrow(580,790,690,790), arrow(930,845,705,940),
             '<text x="42" y="891" font-size="16">Implementation details and control effectiveness must be checked in source code.</text>', '</g></svg>']
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="Render PNG with installed frontend Playwright + Chrome")
    args = parser.parse_args()
    repository = DEST / "repository"
    for path, source in SOURCES.items():
        source = textwrap.dedent(source).lstrip()
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)
        SOURCES[path] = source
        ast.parse(source, filename=path)

    positives = [
        ("V1", "weak_password_hash", "backend/app/core/passwords.py", "hash_password", True,
         "Persisted passwords use one fast SHA-256 digest and a global fixed salt; accounts.register stores the result."),
        ("V2", "sensitive_logging", "backend/app/core/audit.py", "record_signup", True,
         "Registration records raw passwords and complete email addresses in application logs."),
        ("V3", "sql_injection", "backend/app/repositories/users.py", "search_users", True,
         "User-controlled directory query is interpolated into executable SQL; admin authorization does not sanitize SQL."),
        ("V4", "plaintext_pii_export", "backend/jobs/directory_sync.py", "synchronize_directory", False,
         "A separate scheduled job exports users' names, emails and phones to an external HTTP endpoint without TLS."),
    ]
    negatives = [
        ("N1", "weak_password_hash", "backend/app/core/checksums.py", "document_checksum", "SHA-256 hashes document bytes for identity, not passwords."),
        ("N2", "sensitive_logging", "backend/app/core/audit.py", "record_decision", "Decision event excludes raw credentials and contact fields; identifiers may still require access/retention controls."),
        ("N3", "sql_injection", "backend/app/repositories/catalog.py", "list_licenses", "Search input is bound as a query parameter, including embedded SQL punctuation."),
        ("N4", "weak_password_hash", "backend/app/core/recovery.py", "hash_recovery_code", "PBKDF2-HMAC-SHA256 applies 600,000 iterations with a per-secret random salt; SHA-256 usage alone is not a finding."),
    ]
    truth = {
        "schema_version": 1, "dataset_id": "synthetic-lichu-architecture-v1",
        "synthetic": True, "scope": "Four seeded security behaviors and four matched controls; not a complete audit of all possible bugs.",
        "label_method": "Human-authored source-level labels, verified by deterministic behavior checks; never passed to the model.",
        "positives": [dict(id=i, category=c, path=p, function=f, diagram_visible=v, evidence=e, **span(SOURCES[p], f)) for i,c,p,f,v,e in positives],
        "negatives": [dict(id=i, category=c, path=p, function=f, reason=r, **span(SOURCES[p], f)) for i,c,p,f,r in negatives],
        "diagram_omissions": ["backend/jobs/directory_sync.py"],
        "out_of_scope": ["Legal compliance certification", "Real Lichu security claims", "Production concurrency", "All possible findings outside the four benchmark categories"],
    }
    write_json(DEST / "ground_truth.json", truth)
    svg = DEST / "architecture.svg"
    svg.write_text(diagram())
    files = []
    digest = hashlib.sha256()
    for path in sorted(SOURCES):
        raw = (repository / path).read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        files.append({"path": path, "bytes": len(raw), "lines": len(raw.splitlines()), "sha256": checksum})
        digest.update(path.encode() + b"\0" + raw + b"\0")
    write_json(DEST / "manifest.json", {
        "schema_version": 1, "dataset_id": truth["dataset_id"], "synthetic": True,
        "repository": "repository", "diagram": "architecture.png", "diagram_source": "architecture.svg",
        "source_file_count": len(files), "source_bytes": sum(f["bytes"] for f in files),
        "source_lines": sum(f["lines"] for f in files), "source_sha256": digest.hexdigest(),
        "source_hash_method": "SHA256 of sorted UTF8 path + NUL + file bytes + NUL for each source file",
        "diagram_svg_sha256": hashlib.sha256(svg.read_bytes()).hexdigest(),
        "files": files,
    })
    if args.render:
        renderer = '''
            const {chromium} = await import(process.argv[1]);
            const browser = await chromium.launch({channel: 'chrome', headless: true});
            try {
                const page = await browser.newPage({viewport: {width: 1400, height: 1040}, deviceScaleFactor: 1});
                await page.goto(process.argv[2]);
                await page.screenshot({path: process.argv[3]});
            } finally { await browser.close(); }
        '''
        subprocess.run(["node", "--input-type=module", "-e", renderer,
                        (ROOT / "frontend/node_modules/playwright/index.mjs").as_uri(),
                        svg.as_uri(), str(DEST / "architecture.png")], check=True)
    print(json.dumps({"output": str(DEST), "files": len(files), "bytes": sum(f["bytes"] for f in files), "sha256": digest.hexdigest()}))


if __name__ == "__main__":
    main()
