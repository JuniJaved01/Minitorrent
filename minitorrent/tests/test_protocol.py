"""
tests/test_protocol.py  --  OWNER: MAAZ (tests Ayaan's protocol + networking)
Framing tests and a two-peer exchange.   Run:  pytest -v
"""

import socket  # socketpair gives two connected sockets without a real network
import threading  # the slow sender runs in a thread

from common import protocol as P  # code under test
from peer.network import DummyChunkStore, PeerClient, PeerServer, TrackerClient  # code under test
from tests.helpers import LOCAL, start_tracker  # in-process tracker


def test_header_roundtrip():
    a, b = socket.socketpair()  # two ends of one connection
    P.send_msg(a, {"type": P.GET_PEERS, "file_id": "abc"})  # send a header-only message
    header, payload = P.recv_msg(b)  # receive it on the other end
    assert header == {"type": P.GET_PEERS, "file_id": "abc"} and payload is None  # identical, no payload


def test_payload_roundtrip():
    a, b = socket.socketpair()  # two ends
    data = bytes(range(256)) * 1024  # 256 KB of binary data
    threading.Thread(target=P.send_msg, args=(a, {"type": P.CHUNK_DATA, "index": 7}, data)).start()  # send
    header, payload = P.recv_msg(b)  # receive
    assert header["payload_len"] == len(data) and payload == data  # length announced, bytes identical


def test_two_messages_do_not_merge():
    a, b = socket.socketpair()  # two ends
    P.send_msg(a, {"n": 1})  # first message
    P.send_msg(a, {"n": 2}, b"xyz")  # second message directly behind it
    assert P.recv_msg(b) == ({"n": 1}, None)  # framing separates them
    assert P.recv_msg(b) == ({"n": 2, "payload_len": 3}, b"xyz")  # second one intact


def test_message_arriving_byte_by_byte():
    a, b = socket.socketpair()  # two ends
    c, d = socket.socketpair()  # helper pair, used only to capture the frame bytes
    P.send_msg(c, {"type": P.HEARTBEAT, "port": 6001}, b"hello")  # build a frame
    frame = d.recv(4096)  # the raw bytes of that frame

    def slow_sender():  # sends the frame one byte at a time
        for byte in frame:  # every single byte
            a.sendall(bytes([byte]))  # worst-case TCP fragmentation

    threading.Thread(target=slow_sender).start()  # start trickling
    header, payload = P.recv_msg(b)  # recv_exact must loop until complete
    assert header["port"] == 6001 and payload == b"hello"  # still correct


def test_closed_connection_raises():
    a, b = socket.socketpair()  # two ends
    a.sendall(b"\x00\x00")  # only half of the length prefix
    a.close()  # then hang up
    try:  # receiving must fail cleanly
        P.recv_msg(b)  # should raise
        assert False, "expected ProtocolError"  # must not get here
    except P.ProtocolError:  # the expected error
        pass  # good


def test_two_peers_exchange_bitmap_and_chunk_and_tracker_sees_both():
    registry, tracker, tracker_addr = start_tracker()  # in-process tracker
    store_a = DummyChunkStore({0: b"AAAA", 2: b"CCCC"})  # peer A holds chunks 0 and 2
    store_b = DummyChunkStore({1: b"BBBB"})  # peer B holds chunk 1
    peer_a = PeerServer(0, LOCAL).start()  # peer A on a free port
    peer_b = PeerServer(0, LOCAL).start()  # peer B on another free port
    peer_a.add_store("f1", store_a)  # A shares file f1
    peer_b.add_store("f1", store_b)  # B shares file f1
    info = {"file_id": "f1", "name": "x", "size": 12, "num_chunks": 3, "bitmap": "", "chunks_held": 0}  # state
    ta = TrackerClient(tracker_addr, peer_a.port)  # A's tracker helper
    tb = TrackerClient(tracker_addr, peer_b.port)  # B's tracker helper
    assert ta.register(info) and tb.register(info)  # both REGISTER
    assert ta.get_peers("f1") == [(LOCAL, peer_b.port)]  # A sees B (not itself)
    assert tb.get_peers("f1") == [(LOCAL, peer_a.port)]  # B sees A (not itself)
    assert len(registry.peers_snapshot()) == 2  # the tracker sees both
    client = PeerClient()  # download side
    assert client.get_bitmap((LOCAL, peer_a.port), "f1") == [1, 0, 1]  # A's bitmap
    assert client.fetch_chunk((LOCAL, peer_a.port), "f1", 2) == b"CCCC"  # a chunk from A
    assert client.fetch_chunk((LOCAL, peer_b.port), "f1", 1) == b"BBBB"  # a chunk from B
    try:  # asking for a chunk the peer does not hold
        client.fetch_chunk((LOCAL, peer_b.port), "f1", 0)  # B has no chunk 0
        assert False, "expected ProtocolError"  # must not get here
    except P.ProtocolError:  # ERROR reply becomes an exception
        pass  # good
    for s in (peer_a, peer_b, tracker):  # clean up
        s.stop()  # close sockets
