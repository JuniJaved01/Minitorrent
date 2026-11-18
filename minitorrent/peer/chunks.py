"""
peer/chunks.py  --  OWNER: MAAZ
Chunking and integrity: split a file into 256 KB chunks, hash every chunk with
SHA-256, write the .mtorrent metadata file, and store/verify chunks on disk.
"""

import hashlib  # SHA-256 hashing
import json  # the .mtorrent file is JSON
import os  # file sizes and paths
import threading  # the ChunkStore is used by many threads, so it needs a lock

from common import config  # CHUNK_SIZE lives there


def sha256_hex(data):
    """Return the SHA-256 hash of some bytes as a 64-character hex string."""
    return hashlib.sha256(data).hexdigest()  # hash the bytes and format as hex


def create_metadata(path, chunk_size=None):
    """Read a file chunk by chunk and build its metadata dictionary."""
    if chunk_size is None:  # caller did not choose a chunk size
        chunk_size = config.CHUNK_SIZE  # use the project default (256 KB)
    size = os.path.getsize(path)  # total file size in bytes
    hashes = []  # one SHA-256 hex string per chunk, in order
    whole = hashlib.sha256()  # running hash of the WHOLE file (for the final check)
    with open(path, "rb") as f:  # "rb" = read bytes, never text
        while True:  # loop until the file ends
            piece = f.read(chunk_size)  # read the next chunk (the last one may be shorter)
            if not piece:  # empty bytes = end of file
                break  # stop reading
            hashes.append(sha256_hex(piece))  # remember this chunk's hash
            whole.update(piece)  # feed the same bytes into the whole-file hash
    file_id = sha256_hex("".join(hashes).encode("ascii"))  # file_id = SHA-256 of all hashes joined
    return {  # this dictionary IS the .mtorrent content
        "name": os.path.basename(path),  # file name without folders
        "size": size,  # total bytes
        "chunk_size": chunk_size,  # bytes per chunk
        "num_chunks": len(hashes),  # how many chunks the file has
        "hashes": hashes,  # the list of chunk hashes
        "file_id": file_id,  # unique id of this exact content
        "file_hash": whole.hexdigest(),  # SHA-256 of the entire file
    }


def save_metadata(meta, mtorrent_path):
    """Write the metadata dictionary to a .mtorrent file."""
    with open(mtorrent_path, "w", encoding="utf-8") as f:  # open as text for JSON
        json.dump(meta, f, indent=2)  # indent=2 keeps it human-readable
    return mtorrent_path  # handy for the caller


def load_metadata(mtorrent_path):
    """Read a .mtorrent file back into a dictionary."""
    with open(mtorrent_path, "r", encoding="utf-8") as f:  # open as text
        return json.load(f)  # JSON text -> dict


def chunk_length(meta, i):
    """Return how many bytes chunk i has (only the last chunk can be shorter)."""
    start = i * meta["chunk_size"]  # byte offset where chunk i begins
    return min(meta["chunk_size"], meta["size"] - start)  # never run past the end of the file


def read_chunk(path, i, chunk_size=None):
    """Read chunk i straight from a file using seek."""
    if chunk_size is None:  # caller did not choose a chunk size
        chunk_size = config.CHUNK_SIZE  # use the default
    with open(path, "rb") as f:  # open for reading bytes
        f.seek(i * chunk_size)  # jump directly to where chunk i starts
        return f.read(chunk_size)  # read one chunk (shorter at the end of file)


def verify_chunk(meta, i, data):
    """True if the data really is chunk i (its SHA-256 matches the metadata)."""
    if i < 0 or i >= meta["num_chunks"]:  # index outside the file
        return False  # cannot be valid
    return sha256_hex(data) == meta["hashes"][i]  # compare computed hash with the trusted one


def file_sha256(path):
    """SHA-256 of a whole file, read in 1 MB pieces so RAM stays small."""
    h = hashlib.sha256()  # empty running hash
    with open(path, "rb") as f:  # open for reading bytes
        for piece in iter(lambda: f.read(1024 * 1024), b""):  # read 1 MB until empty
            h.update(piece)  # feed each piece into the hash
    return h.hexdigest()  # final hex string


class ChunkStore:
    """
    Thread-safe storage of one file's chunks on disk.
    A SEEDER opens it with complete=True (it already has every chunk).
    A DOWNLOADER opens it with complete=False and fills it chunk by chunk.
    """

    def __init__(self, meta, path, complete=False):
        self.meta = meta  # the trusted metadata (hashes, sizes)
        self.path = path  # where the file lives on disk
        self._lock = threading.Lock()  # protects the bitmap AND the file handle position
        n = meta["num_chunks"]  # number of chunks
        self._bits = [1 if complete else 0] * n  # the bitmap: 1 = we hold that chunk
        if not complete:  # downloader mode
            folder = os.path.dirname(os.path.abspath(path))  # folder that will hold the file
            os.makedirs(folder, exist_ok=True)  # create it if missing
            if not os.path.exists(path):  # brand new download
                with open(path, "wb") as f:  # create the file
                    f.truncate(meta["size"])  # pre-allocate the full size (filled with zeros)

    def has(self, i):
        """True if we hold chunk i."""
        with self._lock:  # read the bitmap safely
            return 0 <= i < len(self._bits) and self._bits[i] == 1  # in range and marked as held

    def bitmap(self):
        """Return a COPY of the bitmap (list of 0/1)."""
        with self._lock:  # read safely
            return list(self._bits)  # copy so callers cannot change our list

    def count(self):
        """How many chunks we hold."""
        with self._lock:  # read safely
            return sum(self._bits)  # 1s add up to the count

    def is_complete(self):
        """True when every chunk is held."""
        with self._lock:  # read safely
            return all(self._bits)  # no zero left

    def read_chunk(self, i):
        """Return the bytes of chunk i (raises KeyError if we do not hold it)."""
        with self._lock:  # one thread at a time touches the file
            if not (0 <= i < len(self._bits)) or self._bits[i] != 1:  # we do not hold it
                raise KeyError("chunk %d not available" % i)  # tell the caller
            with open(self.path, "rb") as f:  # open the data file
                f.seek(i * self.meta["chunk_size"])  # jump to the chunk
                return f.read(chunk_length(self.meta, i))  # read exactly its length

    def write_chunk(self, i, data):
        """Verify and store chunk i. Returns False (and stores nothing) if the hash is wrong."""
        if not verify_chunk(self.meta, i, data):  # integrity check BEFORE touching the disk
            return False  # corrupted or tampered chunk is rejected
        with self._lock:  # one writer at a time
            with open(self.path, "r+b") as f:  # "r+b" = update in place without erasing
                f.seek(i * self.meta["chunk_size"])  # jump to the chunk's position
                f.write(data)  # write the verified bytes
            self._bits[i] = 1  # mark the chunk as held
        return True  # stored successfully

    def recheck_chunk(self, i):
        """Re-hash chunk i from disk (used by resume). Marks and returns the result."""
        with self._lock:  # exclusive access to file and bitmap
            with open(self.path, "rb") as f:  # open the partially downloaded file
                f.seek(i * self.meta["chunk_size"])  # jump to the chunk
                data = f.read(chunk_length(self.meta, i))  # read what is on disk
            good = verify_chunk(self.meta, i, data)  # does it match the trusted hash?
            self._bits[i] = 1 if good else 0  # update the bitmap accordingly
            return good  # tell the caller

    def verify_file(self):
        """Final check: does the whole file hash match the metadata?"""
        with self._lock:  # nobody may write while we hash
            return file_sha256(self.path) == self.meta["file_hash"]  # compare whole-file hashes
