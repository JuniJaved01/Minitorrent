"""
common/netutil.py
Small helpers about this computer's network identity: its name and its LAN IP address.
Used by the tracker (to print a shareable address) and by peers (to tell the tracker who they are).
"""

import ipaddress  # tells us if an address is loopback (127.x.x.x)
import platform  # operating system name for the device list
import socket  # hostname + the UDP trick below


def device_name():
    """The PC name, e.g. 'Alpha-Workstation-01'."""
    return socket.gethostname() or "unknown-pc"  # never empty


def os_name():
    """'Windows', 'Linux' or 'Darwin' (macOS)."""
    return platform.system() or "unknown"  # never empty


def lan_ip():
    """Best guess of this PC's address on the local network (Wi-Fi / Ethernet), e.g. 192.168.1.10.

    We 'connect' a UDP socket to a public address. UDP connect sends NO packet; it only makes the
    operating system choose the network card it WOULD use, and we read that card's address.
    Without any network we fall back to 127.0.0.1 (this PC only).
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP socket
    try:  # fails when there is no network at all
        s.connect(("10.255.255.255", 1))  # any non-local address works, nothing is sent
        ip = s.getsockname()[0]  # the address of the chosen network card
    except OSError:  # offline
        ip = "127.0.0.1"  # loopback only
    finally:  # always free the socket
        s.close()  # done
    return ip  # e.g. '192.168.1.10'


def is_loopback(ip):
    """True for 127.0.0.1 and friends (traffic that never leaves this PC)."""
    try:  # the text may not be an IP at all
        return ipaddress.ip_address(ip).is_loopback  # 127.0.0.0/8 or ::1
    except ValueError:  # a hostname such as 'localhost'
        return ip == "localhost"  # treat the name like the address
