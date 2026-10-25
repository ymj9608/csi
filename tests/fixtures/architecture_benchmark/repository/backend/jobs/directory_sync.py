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
