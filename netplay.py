"""
netplay.py  --  2-player online play for Spicy John over WiFi / LAN / phone hotspot.
No pygame in here: pure sockets, so it can be tested without a window.

How it works
------------
* Discovery : the host broadcasts a tiny UDP beacon (port 45454) every second, the joiner listens.
              Fallbacks: type the host IP by hand, or auto-probe the gateway (phone hotspot = x.x.x.1).
* Link      : one TCP connection (port 45455), newline-delimited JSON, read by a background thread.
* Gameplay  : LOCKSTEP.  Both devices run the exact same simulation (same random seed, same chapter);
              only the *inputs* travel over the network (a few bytes per frame).  Inputs are applied
              `delay` frames after they were made so both sides always have them in time.
              The host also sends a small player snapshot now and then as a safety net.
"""
import socket, threading, json, time, collections, random

VERSION = 1
PORT_UDP = 45454
PORT_TCP = 45455
MAGIC = "SPICYJOHN"
HELD_BITS = (("left", 1), ("right", 2), ("up", 4), ("down", 8))


# ------------------------------------------------------------------------------------------------
#  helpers
# ------------------------------------------------------------------------------------------------
def local_ips():
    """Best-effort list of this device's IPv4 addresses (works without internet)."""
    out = []

    def add(ip):
        if ip and not ip.startswith("127.") and not ip.startswith("169.254.") and ip not in out:
            out.append(ip)

    for target in ("10.255.255.255", "192.168.255.255", "172.31.255.255", "8.8.8.8"):
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.2)
            s.connect((target, 9))
            add(s.getsockname()[0])
        except Exception:
            pass
        finally:
            try: s.close()
            except Exception: pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            add(ip)
    except Exception:
        pass
    # Android: ask the system (pyjnius) - catches the hotspot interface too
    try:
        import netifaces                                   # optional, never required
        for ifc in netifaces.interfaces():
            for a in netifaces.ifaddresses(ifc).get(netifaces.AF_INET, []):
                add(a.get("addr"))
    except Exception:
        pass
    return out


def broadcast_targets():
    """Addresses a beacon should be sent to (global + directed broadcasts of every local subnet)."""
    t = ["255.255.255.255"]
    for ip in local_ips():
        p = ip.split(".")
        if len(p) == 4:
            t.append("%s.%s.%s.255" % (p[0], p[1], p[2]))
    for extra in ("192.168.43.255", "192.168.49.255", "192.168.137.255", "172.20.10.255"):   # common hotspot subnets
        t.append(extra)
    seen = []
    for x in t:
        if x not in seen: seen.append(x)
    return seen


_multicast_lock = None
def acquire_multicast_lock():
    """Android drops broadcast packets to save battery unless this lock is held."""
    global _multicast_lock
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Context = autoclass("android.content.Context")
        wifi = PythonActivity.mActivity.getSystemService(Context.WIFI_SERVICE)
        _multicast_lock = wifi.createMulticastLock("spicyjohn")
        _multicast_lock.setReferenceCounted(False)
        _multicast_lock.acquire()
    except Exception:
        pass


# ------------------------------------------------------------------------------------------------
#  Link  (one TCP connection, JSON lines)
# ------------------------------------------------------------------------------------------------
class Link:
    def __init__(self, sock, peer_ip):
        self.sock = sock; self.peer_ip = peer_ip
        self.inbox = collections.deque()
        self.closed = False; self.err = ""
        self.last_rx = time.time(); self.lock = threading.Lock()
        try: sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception: pass
        try: sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except Exception: pass
        sock.settimeout(None)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        buf = b""
        try:
            while not self.closed:
                data = self.sock.recv(65536)
                if not data:
                    break
                self.last_rx = time.time()
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line:
                        try: self.inbox.append(json.loads(line.decode("utf-8")))
                        except Exception: pass
        except Exception as ex:
            self.err = str(ex)
        self.closed = True

    def send(self, msg):
        if self.closed: return False
        try:
            data = (json.dumps(msg, separators=(",", ":")) + "\n").encode("utf-8")
            with self.lock: self.sock.sendall(data)
            return True
        except Exception as ex:
            self.err = str(ex); self.closed = True
            return False

    def poll(self):
        """pop one message (or None)"""
        try: return self.inbox.popleft()
        except IndexError: return None

    def silent_for(self):
        return time.time() - self.last_rx

    def close(self, say_bye=True):
        if say_bye and not self.closed: self.send({"t": "bye"})
        self.closed = True
        try: self.sock.shutdown(socket.SHUT_RDWR)
        except Exception: pass
        try: self.sock.close()
        except Exception: pass


# ------------------------------------------------------------------------------------------------
#  Host: TCP listener + UDP beacon
# ------------------------------------------------------------------------------------------------
class Host:
    def __init__(self, name="Player"):
        self.name = name; self.link = None; self.peer_name = ""; self.error = ""
        self.stop = False; self.port = PORT_TCP
        self.ips = local_ips()
        acquire_multicast_lock()
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.srv.bind(("", PORT_TCP))
        except OSError:
            self.srv.bind(("", 0)); self.port = self.srv.getsockname()[1]
        self.srv.listen(2); self.srv.settimeout(0.5)
        threading.Thread(target=self._accept, daemon=True).start()
        threading.Thread(target=self._beacon, daemon=True).start()

    def _accept(self):
        while not self.stop and self.link is None:
            try:
                c, addr = self.srv.accept()
            except socket.timeout:
                continue
            except Exception as ex:
                self.error = str(ex); return
            try:
                c.settimeout(3.0)
                raw = b""
                while b"\n" not in raw:                      # wait for the guest's hello
                    d = c.recv(4096)
                    if not d: raise IOError("closed")
                    raw += d
                line, rest = raw.split(b"\n", 1)
                hello = json.loads(line.decode("utf-8"))
                if hello.get("t") != "hello" or hello.get("magic") != MAGIC:
                    c.close(); continue
                if hello.get("ver") != VERSION:
                    c.sendall((json.dumps({"t": "reject", "why": "Different game version"}) + "\n").encode()); c.close(); continue
                c.sendall((json.dumps({"t": "welcome", "name": self.name, "ver": VERSION}) + "\n").encode())
                self.peer_name = str(hello.get("name", "Player"))[:16]
                lk = Link(c, addr[0])
                for extra in rest.split(b"\n"):               # anything that came right behind the hello
                    if extra:
                        try: lk.inbox.append(json.loads(extra.decode("utf-8")))
                        except Exception: pass
                self.link = lk
            except Exception:
                try: c.close()
                except Exception: pass

    def _beacon(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try: s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except Exception: pass
        n = 0
        while not self.stop and self.link is None:
            if n % 10 == 0: targets = broadcast_targets()
            n += 1
            msg = json.dumps({"magic": MAGIC, "ver": VERSION, "name": self.name, "port": self.port}).encode()
            for t in targets:
                try: s.sendto(msg, (t, PORT_UDP))
                except Exception: pass
            time.sleep(1.0)
        try: s.close()
        except Exception: pass

    def close(self):
        self.stop = True
        try: self.srv.close()
        except Exception: pass


# ------------------------------------------------------------------------------------------------
#  Guest: scanner + connect
# ------------------------------------------------------------------------------------------------
class Scanner:
    """Listens for host beacons and (optionally) probes the gateway.  `found` = {ip: (name, port, last_seen)}"""
    def __init__(self):
        self.found = {}; self.stop = False
        acquire_multicast_lock()
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._probe_gateway, daemon=True).start()

    def _listen(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try: s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception: pass
            s.bind(("", PORT_UDP)); s.settimeout(0.5)
        except Exception:
            return
        while not self.stop:
            try:
                data, addr = s.recvfrom(1024)
                m = json.loads(data.decode("utf-8"))
                if m.get("magic") == MAGIC and m.get("ver") == VERSION:
                    self.found[addr[0]] = (str(m.get("name", "Host"))[:16], int(m.get("port", PORT_TCP)), time.time())
            except socket.timeout:
                continue
            except Exception:
                continue
        try: s.close()
        except Exception: pass

    def _probe_gateway(self):
        """A phone hotspot is always x.x.x.1 - try it even if broadcasts are blocked."""
        time.sleep(1.5)
        for ip in local_ips():
            p = ip.split(".")
            if len(p) != 4: continue
            gw = "%s.%s.%s.1" % (p[0], p[1], p[2])
            if gw == ip or gw in self.found: continue
            try:
                c = socket.create_connection((gw, PORT_TCP), timeout=1.0)
                c.close()
                if gw not in self.found: self.found[gw] = ("Host (gateway)", PORT_TCP, time.time())
            except Exception:
                pass

    def hosts(self):
        now = time.time()
        for ip in [i for i, v in self.found.items() if now - v[2] > 6 and not v[0].startswith("Host (gateway")]:
            self.found.pop(ip, None)
        return sorted([(ip, v[0], v[1]) for ip, v in self.found.items()])

    def close(self): self.stop = True


def connect(ip, port, name="Player", timeout=4.0):
    """Returns (Link, host_name).  Raises IOError with a readable message."""
    try:
        c = socket.create_connection((ip, port), timeout=timeout)
    except Exception as ex:
        raise IOError("Can't reach %s  (%s)" % (ip, ex.__class__.__name__))
    try:
        c.settimeout(timeout)
        c.sendall((json.dumps({"t": "hello", "magic": MAGIC, "ver": VERSION, "name": name}) + "\n").encode())
        raw = b""
        while b"\n" not in raw:
            d = c.recv(4096)
            if not d: raise IOError("Host closed the connection")
            raw += d
        line, rest = raw.split(b"\n", 1)
        m = json.loads(line.decode("utf-8"))
        if m.get("t") == "reject": raise IOError(str(m.get("why", "Rejected")))
        if m.get("t") != "welcome": raise IOError("Not a Spicy John host")
        lk = Link(c, ip)
        for extra in rest.split(b"\n"):
            if extra:
                try: lk.inbox.append(json.loads(extra.decode("utf-8")))
                except Exception: pass
        return lk, str(m.get("name", "Host"))[:16]
    except IOError:
        try: c.close()
        except Exception: pass
        raise
    except Exception as ex:
        try: c.close()
        except Exception: pass
        raise IOError("Connection failed (%s)" % ex.__class__.__name__)


# ------------------------------------------------------------------------------------------------
#  Lockstep  (input exchange for one match)
# ------------------------------------------------------------------------------------------------
EMPTY = (0, ())


def pack_held(held):
    return sum(b for k, b in HELD_BITS if held.get(k))


def unpack_held(bits):
    return {k: bool(bits & b) for k, b in HELD_BITS}


class Lockstep:
    """
    frame ........ the simulation frame about to be played
    submit() ..... once per frame: send my input for frame+delay
    ready() ...... True when the other player's input for `frame` is here
    advance() .... frame += 1
    Player 1 = host, player 2 = guest.
    """
    SYNC_EVERY = 30

    def __init__(self, link, is_host, seed, delay=4):
        self.link = link; self.host = is_host; self.seed = seed; self.D = delay
        self.frame = 0; self.submitted = -1
        self.mine = {}; self.theirs = {}
        for f in range(delay):
            self.mine[f] = EMPTY; self.theirs[f] = EMPTY
        self.hist = {}; self.sync_in = []; self.peer_left = False
        self.stall = 0; self.fixes = 0; self.checks = 0
        self.seeded = False; self.finished = False

    # -- network ---------------------------------------------------------------------------------
    def pump(self):
        while True:
            m = self.link.poll()
            if m is None: break
            t = m.get("t")
            if t == "i":
                self.theirs[int(m["f"])] = (int(m["h"]), tuple(m.get("p", ())))
            elif t == "s":
                self.sync_in.append(m)
            elif t == "bye":
                self.peer_left = True
        if self.link.closed: self.peer_left = True

    def submit(self, held_bits, presses):
        if self.submitted == self.frame: return
        self.submitted = self.frame
        f = self.frame + self.D
        self.mine[f] = (held_bits, tuple(presses))
        self.link.send({"t": "i", "f": f, "h": held_bits, "p": list(presses)})

    def ready(self):
        return self.frame in self.theirs and self.frame in self.mine

    def inputs(self):
        """((held_bits, presses) for P1, same for P2)"""
        a, b = self.mine[self.frame], self.theirs[self.frame]
        return (a, b) if self.host else (b, a)

    def advance(self):
        self.mine.pop(self.frame, None); self.theirs.pop(self.frame, None)
        self.hist.pop(self.frame - 90, None)
        self.frame += 1

    # -- safety net: host snapshot -----------------------------------------------------------------
    def snapshot_out(self, players):
        if self.host and self.frame % self.SYNC_EVERY == 0 and self.frame > 0:
            self.link.send({"t": "s", "f": self.frame, "p": [[round(p.x, 2), round(p.y, 2), round(p.hp, 2), round(p.energy, 2)] for p in players]})
        if not self.host: self.hist[self.frame] = [(p.x, p.y, p.hp, p.energy) for p in players]

    def snapshot_in(self, players):
        """guest: compare the host's state of an earlier frame with ours and nudge by the difference"""
        if self.host: self.sync_in = []; return
        keep = []
        for m in self.sync_in:
            f = m["f"]
            if f > self.frame: keep.append(m); continue
            mine = self.hist.get(f)
            if not mine: continue
            self.checks += 1
            bad = False
            for p, h, st in zip(players, m["p"], mine):
                dx, dy, dh, de = h[0] - st[0], h[1] - st[1], h[2] - st[2], h[3] - st[3]
                if abs(dx) > 1.0 or abs(dy) > 1.0 or abs(dh) > 0.5 or abs(de) > 1.0:
                    bad = True; p.x += dx; p.y += dy; p.hp += dh; p.energy += de
            if bad: self.fixes += 1
        self.sync_in = keep

    def close(self):
        self.finished = True


def new_seed():
    return random.SystemRandom().randrange(1, 2 ** 31)
