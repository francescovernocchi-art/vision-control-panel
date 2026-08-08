from database.db import Database

db = Database()
with db.connect() as conn:
    cur = conn.execute(
        "DELETE FROM imap_processed WHERE entry_id = ?",
        ("INBOX.MdA_Eni:6",),
    )
    print("deleted", cur.rowcount)
