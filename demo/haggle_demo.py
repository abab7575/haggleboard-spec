#!/usr/bin/env python3
"""HaggleBoard Protocol (HBP) v0 demo: one shopper agent, two seller agents.
Rule-based. No money moves: the result is a signed deal token handed to checkout (UCP/ACP)."""
import json, hashlib, base64, secrets, uuid, os, sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.exceptions import InvalidSignature

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMAS = os.path.join(HERE, "..", "schemas")
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)  # fixed clock -> reproducible transcript
CLOCK = [NOW]
def now(): return CLOCK[0]
def tick(s=2): CLOCK[0] += timedelta(seconds=s)
def iso(t): return t.strftime("%Y-%m-%dT%H:%M:%SZ")
def money(x, cur): return {"amount": str(Decimal(x).quantize(Decimal("0.01"), ROUND_HALF_UP)), "currency": cur}
def canon(obj): return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
def b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
def unb64(s): return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

# ---- minimal schema check (required/const/enum/$ref); uses jsonschema if installed ----
def load(name): return json.load(open(os.path.join(SCHEMAS, name + ".json")))
def check(inst, sch, root, path="$"):
    if "$ref" in sch: sch = root["$defs"][sch["$ref"].split("/")[-1]]
    if "const" in sch and inst != sch["const"]: raise ValueError(f"{path}: expected {sch['const']}")
    if "enum" in sch and inst not in sch["enum"]: raise ValueError(f"{path}: {inst} not in enum")
    if sch.get("type") == "object":
        for r in sch.get("required", []):
            if r not in inst: raise ValueError(f"{path}: missing '{r}'")
        for k, v in sch.get("properties", {}).items():
            if k in inst: check(inst[k], v, root, f"{path}.{k}")
def validate(msg):
    sch = load(msg["type"])
    try:
        import jsonschema; jsonschema.validate(msg, sch)
    except ImportError:
        check(msg, sch, sch)
    cat = (msg.get("terms") or msg.get("need") or {}).get("category")
    item = (msg.get("terms") or msg.get("need") or {}).get("item")
    if cat and item is not None: check(item, load("ext-" + cat), {})

# ---- agents ----
class Agent:
    def __init__(self, agent_id, role):
        self.agent_id, self.role = agent_id, role
        self.key = Ed25519PrivateKey.generate(); self.pub = self.key.public_key()
        self.seen_nonces = set()
    def sign(self, body):
        return {"alg": "Ed25519", "key_id": self.agent_id + "#k1", "value": b64(self.key.sign(canon(body)))}
    def msg(self, typ, thread, reply_to=None, sign=False, **fields):
        m = {"hbp": "0.1", "type": typ, "thread_id": thread, "message_id": "m_" + uuid.uuid4().hex[:10],
             "sent_at": iso(now()), "from": {"agent_id": self.agent_id, "role": self.role},
             "nonce": secrets.token_hex(12), **fields}
        if reply_to: m["in_reply_to"] = reply_to
        if sign: m["signature"] = self.sign(m)
        return m
    def receive(self, m, directory):
        """Every receiver runs the same checks: schema, signature, nonce, expiry."""
        validate(m)
        if "expires_at" in m and m["expires_at"] < iso(now()): raise ValueError("message expired")
        if "signature" in m:
            body = {k: v for k, v in m.items() if k != "signature"}
            try: directory[m["from"]["agent_id"]].pub.verify(unb64(m["signature"]["value"]), canon(body))
            except InvalidSignature: raise ValueError("bad signature")
        key = (m["from"]["agent_id"], m["nonce"])
        if key in self.seen_nonces: raise ValueError("replayed nonce")
        self.seen_nonces.add(key)

class Seller(Agent):
    def __init__(self, agent_id, list_price, floor, step, checkout):
        super().__init__(agent_id, "seller")
        self.list, self.floor, self.step, self.checkout = Decimal(list_price), Decimal(floor), Decimal(step), checkout
        self.last = None
    def respond(self, buyer_price, rnd):
        """Concede `step` of the remaining gap each round, never below floor (private)."""
        if self.last is None: self.last = self.list; return ("offer", self.last)
        if buyer_price is not None and buyer_price >= self.floor and buyer_price >= self.last - self.list * Decimal("0.02"):
            return ("accept", buyer_price)
        nxt = max(self.floor, self.last - (self.last - max(buyer_price or 0, self.floor)) * self.step)
        self.last = nxt.quantize(Decimal("1"))
        return ("counter", self.last)

class Shopper(Agent):
    def __init__(self): super().__init__("did:web:shopper.example", "buyer")
    def plan(self, target, ceiling): self.target, self.ceiling, self.bid = Decimal(target), Decimal(ceiling), None
    def respond(self, ask, rnd, max_rounds):
        if ask <= self.target or (ask <= self.ceiling and rnd >= max_rounds - 1): return ("accept", ask)
        self.bid = self.target if self.bid is None else min(self.ceiling, self.bid + (ask - self.bid) * Decimal("0.35"))
        self.bid = self.bid.quantize(Decimal("1"))
        if rnd >= max_rounds: return ("decline", None)
        return ("counter", self.bid)

# ---- transcript ----
def say(m, note=""):
    who = m["from"]["agent_id"].replace("did:web:", "")
    t = m.get("terms", {}).get("price") or m.get("need", {}).get("budget_max")
    p = f" {t['currency']} {t['amount']}" if t and m["type"] != "request" else ""
    sig = " [signed]" if "signature" in m else ""
    print(f"  {m['sent_at'][11:19]}  {who:<26} {m['type'].upper():<8}{p}{sig}  {note}")

def negotiate(shopper, seller, category, item, cur, target, ceiling, max_rounds=6):
    D = {a.agent_id: a for a in (shopper, seller)}
    thread = "t_" + uuid.uuid4().hex[:8]
    shopper.plan(target, ceiling)
    exp = lambda mins=10: iso(now() + timedelta(minutes=mins))
    req = shopper.msg("request", thread, need={"category": category, "item": item, "quantity": 1}, expires_at=exp(30), max_rounds=max_rounds)
    seller.receive(req, D); say(req, f"needs: {describe(category, item)}")
    last, rnd, bid = req, 0, None
    while True:
        tick(); rnd += 1
        kind, price = seller.respond(bid, rnd)
        if kind == "accept":
            return close(seller, shopper, last, D, thread)
        m = seller.msg(kind, thread, last["message_id"], sign=True, round=rnd, expires_at=exp(),
                       terms={"category": category, "item": item, "price": money(price, cur)})
        shopper.receive(m, D); say(m, ("(seller's limit stays private)" if RECORDING else "(floor stays private)") if rnd == 1 else ""); last = m
        tick()
        kind, bid = shopper.respond(price, rnd, max_rounds)
        if kind == "accept":
            return close(shopper, seller, last, D, thread)
        if kind == "decline":
            m = shopper.msg("decline", thread, last["message_id"], reason="price"); seller.receive(m, D); say(m); return None
        m = shopper.msg("counter", thread, last["message_id"], sign=True, round=rnd, expires_at=exp(),
                        terms={"category": category, "item": item, "price": money(bid, cur)})
        seller.receive(m, D); say(m); last = m

def close(acceptor, other, accepted, D, thread):
    terms = accepted["terms"]; th = hashlib.sha256(canon(terms)).hexdigest()
    seller = acceptor if acceptor.role == "seller" else other
    token = {"terms": terms, "terms_hash": th, "valid_until": iso(now() + timedelta(minutes=15)),
             "handoff": seller.checkout}
    token["seller_signature"] = seller.sign({k: token[k] for k in ("terms", "terms_hash", "valid_until", "handoff")})
    m = acceptor.msg("accept", thread, accepted["message_id"], sign=True, accepted_message_id=accepted["message_id"],
                     terms_hash=th, deal_token=token)
    other.receive(m, D); say(m, "deal locked")
    print(f"  -> HANDOFF to {token['handoff']['protocol'].upper()} checkout: {token['handoff']['endpoint']}")
    print(f"     deal_token terms_hash={th[:16]}…  valid_until={token['valid_until']}  (HBP never touches payment)")
    return terms["price"]

def describe(cat, it):
    if cat == "hotel": return f"{it['room_type']}, {it['check_in']}→{it['check_out']}, {it['guests']} guests, {it['cancellation']}"
    if cat == "electronics": return f"GTIN {it['gtin']} ({it['condition']}, {it['warranty_months']}m warranty)"
    return json.dumps(it)

RECORDING = False

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="HaggleBoard Protocol v0 demo")
    ap.add_argument("--recording", action="store_true", help="public-safe output: never print seller floors or shopper ceilings")
    global RECORDING
    rec = RECORDING = ap.parse_args(argv).recording
    shopper = Shopper()
    hotel = Seller("did:web:harbourhotel.example", 240, 185, Decimal("0.4"),
                   {"protocol": "ucp", "endpoint": "https://harbourhotel.example/.well-known/ucp"})
    shop = Seller("did:web:laptops.example", 1299, 1120, Decimal("0.35"),
                  {"protocol": "acp", "endpoint": "https://laptops.example/checkout_sessions"})
    print("HaggleBoard Protocol v0 demo  (rule-based agents; Ed25519-signed offers; nonce + expiry enforced)\n")
    print("Deal 1: hotel stay  | seller list EUR 240/night" + ("" if rec else ", private floor EUR 185 | shopper target 170, ceiling 205"))
    p1 = negotiate(shopper, hotel, "hotel",
        {"property_id": "harbourhotel-dub-01", "check_in": "2026-11-13", "check_out": "2026-11-15",
         "room_type": "double", "guests": 2, "cancellation": "free_until_24h", "breakfast": True},
        "EUR", 170, 205)
    print("\nDeal 2: laptop      | seller list EUR 1299" + ("" if rec else ", private floor EUR 1120 | shopper target 1050, ceiling 1180"))
    p2 = negotiate(shopper, shop, "electronics",
        {"gtin": "0000000000000", "condition": "new", "warranty_months": 24, "shipping_days": 2, "returns_days": 30},
        "EUR", 1050, 1180)
    print("\nSafety checks")
    D = {a.agent_id: a for a in (shopper, hotel)}
    m = hotel.msg("offer", "t_x", "m_x", sign=True, round=1, expires_at=iso(now() + timedelta(minutes=5)),
                  terms={"category": "electronics", "item": {"gtin": "1", "condition": "new"}, "price": money(1, "EUR")})
    shopper.receive(m, D)
    for label, mut in [("replayed nonce", lambda x: x),
                       ("tampered price", lambda x: {**x, "nonce": secrets.token_hex(12), "terms": {**x["terms"], "price": money(0.5, "EUR")}}),
                       ("expired offer", lambda x: {**x, "nonce": secrets.token_hex(12), "expires_at": "2020-01-01T00:00:00Z"})]:
        try: shopper.receive(mut(m), D); print(f"  FAIL {label} accepted")
        except ValueError as e: print(f"  ok   {label} rejected ({e})")
    print("\nSummary")
    print(f"  hotel : {'EUR ' + p1['amount'] + '/night (list 240' + ('' if rec else ', floor 185') + ')' if p1 else 'no deal'}")
    print(f"  laptop: {'EUR ' + p2['amount'] + ' (list 1299' + ('' if rec else ', floor 1120') + ')' if p2 else 'no deal'}")

if __name__ == "__main__":
    main()
