"""
tracker/storage.py  --  OWNER: ARBAB
SQLite persistence for the tracker, so the registry survives a restart.
Two tables:  files (one row per shared file)  and  peers (one row per peer per file).
"""

import json  # the 'extra' column stores a JSON string
import sqlite3  # built into python, no server needed
import threading  # sqlite connection is shared between threads, so we lock it


class Storage:
    """A tiny wrapper around one SQLite database file."""

    def __init__(self, db_path):
        self._lock = threading.Lock()  # only one thread talks to sqlite at a time
        self._db = sqlite3.connect(db_path, check_same_thread=False)  # allow use from many threads
        with self._lock:  # create the tables once
            self._db.execute(  # table 1: the files the swarm knows
                "CREATE TABLE IF NOT EXISTS files ("
                "file_id TEXT PRIMARY KEY, name TEXT, size INTEGER, num_chunks INTEGER)"
            )
            self._db.execute(  # table 2: the peers of every file
                "CREATE TABLE IF NOT EXISTS peers ("
                "file_id TEXT, ip TEXT, port INTEGER, last_seen REAL, chunks_held INTEGER, "
                "bitmap TEXT, uploaded INTEGER, downloaded INTEGER, extra TEXT, "
                "PRIMARY KEY (file_id, ip, port))"
            )
            self._db.commit()  # make the tables permanent

    def save_file(self, f):
        """Insert or update one file row."""
        with self._lock:  # exclusive access
            self._db.execute(  # REPLACE = insert, or overwrite the row with the same primary key
                "INSERT OR REPLACE INTO files VALUES (?, ?, ?, ?)",
                (f["file_id"], f["name"], f["size"], f["num_chunks"]),  # '?' placeholders prevent SQL injection
            )
            self._db.commit()  # write to disk

    def save_peer(self, p):
        """Insert or update one peer row."""
        with self._lock:  # exclusive access
            self._db.execute(  # one row per (file, ip, port)
                "INSERT OR REPLACE INTO peers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (p["file_id"], p["ip"], p["port"], p["last_seen"], p["chunks_held"],
                 p["bitmap"], p["uploaded"], p["downloaded"], json.dumps(p["extra"])),
            )
            self._db.commit()  # write to disk

    def delete_peer(self, file_id, ip, port):
        """Remove a peer row (called when the peer timed out)."""
        with self._lock:  # exclusive access
            self._db.execute("DELETE FROM peers WHERE file_id=? AND ip=? AND port=?", (file_id, ip, port))  # delete
            self._db.commit()  # write to disk

    def load_files(self):
        """Return every file row as a list of dicts."""
        with self._lock:  # exclusive access
            rows = self._db.execute("SELECT file_id, name, size, num_chunks FROM files").fetchall()  # all rows
        return [{"file_id": r[0], "name": r[1], "size": r[2], "num_chunks": r[3]} for r in rows]  # tuples -> dicts

    def load_peers(self):
        """Return every peer row as a list of dicts."""
        with self._lock:  # exclusive access
            rows = self._db.execute(  # all peer rows
                "SELECT file_id, ip, port, last_seen, chunks_held, bitmap, uploaded, downloaded, extra FROM peers"
            ).fetchall()
        return [  # tuples -> dicts
            {"file_id": r[0], "ip": r[1], "port": r[2], "last_seen": r[3], "chunks_held": r[4],
             "bitmap": r[5], "uploaded": r[6], "downloaded": r[7], "extra": json.loads(r[8] or "{}")}
            for r in rows
        ]

    def close(self):
        """Close the database file."""
        with self._lock:  # exclusive access
            self._db.close()  # release the file
