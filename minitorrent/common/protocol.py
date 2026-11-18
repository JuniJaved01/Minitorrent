"""
common/protocol.py  --  OWNER: AYAAN
The MiniTorrent application-layer protocol.

WHY FRAMING?  TCP is a byte STREAM, it has no idea where one message ends.
So every message on the wire looks like this:

    +----------------+---------------------------+----------------------+
    | 4 bytes length | JSON header (that length) | raw payload (optional)|
    +----------------+---------------------------+----------------------+

The 4-byte length is big-endian ('>I').  If the message carries file data,
the JSON header contains "payload_len" and exactly that many raw bytes follow.
"""

import json  # turns python dicts into text and back
import socket  # TCP sockets
import struct  # packs numbers into fixed-size bytes

from common import config  # shared settings (timeouts, size limits)

# ---- message types: peer <-> tracker ----
REGISTER = "REGISTER"  # peer -> tracker : "I exist and I hold this file"
GET_PEERS = "GET_PEERS"  # peer -> tracker : "who has this file?"
HEARTBEAT = "HEARTBEAT"  # peer -> tracker : "I am still alive, here is my progress"
PEERS = "PEERS"  # tracker -> peer : the answer to GET_PEERS
OK = "OK"  # tracker -> peer : generic "done"
# ---- message types: peer <-> peer ----
HAVE_BITMAP = "HAVE_BITMAP"  # request AND reply: "which chunks do you hold?"
REQUEST_CHUNK = "REQUEST_CHUNK"  # "send me chunk number i"
CHUNK_DATA = "CHUNK_DATA"  # reply: header + the raw chunk bytes
# ---- used by everyone ----
ERROR = "ERROR"  # something went wrong, see the "reason" field

LENGTH_FORMAT = ">I"  # '>' = big-endian (network byte order), 'I' = unsigned 4-byte int
LENGTH_SIZE = struct.calcsize(LENGTH_FORMAT)  # = 4 bytes


class ProtocolError(Exception):
    """Raised when the other side breaks the protocol or closes the connection."""


def recv_exact(sock, n):
    """Receive EXACTLY n bytes. recv() may return fewer bytes, so we loop."""
    parts = []  # the pieces we received so far
    remaining = n  # how many bytes are still missing
    while remaining > 0:  # keep going until nothing is missing
        piece = sock.recv(min(remaining, 65536))  # ask for the rest (max 64 KB per call)
        if not piece:  # empty bytes means the other side closed the connection
            raise ProtocolError("connection closed before the full message arrived")  # report it
        parts.append(piece)  # remember this piece
        remaining -= len(piece)  # fewer bytes are missing now
    return b"".join(parts)  # glue all pieces into one bytes object


def send_msg(sock, header, payload=None):
    """Send one message: 4-byte length + JSON header (+ raw payload if given)."""
    header = dict(header)  # copy so we never change the caller's dict
    if payload is not None:  # this message carries file data
        header["payload_len"] = len(payload)  # tell the receiver how many raw bytes follow
    body = json.dumps(header).encode("utf-8")  # dict -> JSON text -> bytes
    frame = struct.pack(LENGTH_FORMAT, len(body)) + body  # prefix the JSON with its 4-byte length
    if payload is not None:  # add the raw bytes right after the JSON
        frame += payload  # one buffer = one sendall = fewer tiny packets
    sock.sendall(frame)  # sendall loops internally until every byte is sent


def recv_msg(sock):
    """Receive one message. Returns (header_dict, payload_bytes_or_None)."""
    raw_len = recv_exact(sock, LENGTH_SIZE)  # step 1: read the 4-byte length prefix
    (body_len,) = struct.unpack(LENGTH_FORMAT, raw_len)  # 4 bytes -> python int
    if body_len > config.MAX_HEADER_BYTES:  # protect ourselves from a crazy/hostile length
        raise ProtocolError("header too large: %d bytes" % body_len)  # refuse the message
    body = recv_exact(sock, body_len)  # step 2: read exactly that many JSON bytes
    try:  # the bytes might not be valid JSON
        header = json.loads(body.decode("utf-8"))  # bytes -> text -> dict
    except ValueError as exc:  # bad JSON or bad utf-8
        raise ProtocolError("header is not valid JSON") from exc  # report it as a protocol error
    payload = None  # most messages have no payload
    payload_len = header.get("payload_len", 0)  # how many raw bytes follow (0 if none)
    if payload_len:  # step 3: there is file data after the header
        if payload_len > config.MAX_PAYLOAD_BYTES:  # protect ourselves again
            raise ProtocolError("payload too large: %d bytes" % payload_len)  # refuse the message
        payload = recv_exact(sock, payload_len)  # read exactly the raw bytes
    return header, payload  # hand both back to the caller


def request(addr, header, payload=None, timeout=None):
    """Client helper: connect, send ONE message, wait for ONE reply, disconnect."""
    if timeout is None:  # caller did not choose a timeout
        timeout = config.SOCKET_TIMEOUT  # use the default (5 seconds)
    with socket.create_connection(addr, timeout=timeout) as sock:  # TCP 3-way handshake happens here
        sock.settimeout(timeout)  # also limit how long each recv/send may block
        send_msg(sock, header, payload)  # send our question
        return recv_msg(sock)  # return the answer (socket closes automatically)


def parse_addr(text, default_port=None):
    """Turn 'host:port' text into a ('host', port) tuple."""
    if ":" in text:  # the text has a port part
        host, port = text.rsplit(":", 1)  # split on the LAST colon
        return host, int(port)  # port must be an int
    return text, default_port  # no port given, use the default
