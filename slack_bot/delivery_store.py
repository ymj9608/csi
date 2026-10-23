"""Per-recipient receipts survive poll failures and process restarts."""
import sqlite3
from pathlib import Path


class DeliveryStore:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS deliveries (
            approval_id TEXT, user_id TEXT, channel TEXT NOT NULL, ts TEXT NOT NULL,
            status TEXT NOT NULL, PRIMARY KEY(approval_id,user_id))""")
        self.db.commit()

    def get(self, approval_id, user_id):
        return self.db.execute("SELECT channel,ts,status FROM deliveries WHERE approval_id=? AND user_id=?",
                               (approval_id, user_id)).fetchone()

    def save(self, approval_id, user_id, channel, ts, status):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO deliveries VALUES(?,?,?,?,?)",
                            (approval_id, user_id, channel, ts, status))

    def messages(self, approval_id):
        return self.db.execute("SELECT user_id,channel,ts,status FROM deliveries WHERE approval_id=?",
                               (approval_id,)).fetchall()

    def close(self):
        self.db.close()
