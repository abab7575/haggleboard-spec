# HaggleBoard Protocol (HBP) v0

**Pitch.** AI agents can already find products (MCP), talk to each other (A2A) and pay (UCP, ACP, AP2), but no open standard lets them agree a *price*. HaggleBoard is that missing layer: a small, category-agnostic set of signed messages (Request, Offer, Counter, Accept, Decline, Expire) so any buyer agent can negotiate with any seller agent: a hotel room tonight, an open-box laptop, or a 12-month B2B supply contract. Once both sides agree, the signed deal token goes straight into existing checkout rails. HBP never touches money and charges no fees. It is the handshake that comes before the payment, and it aims to be for agent deal-making what HTTP is for the web.

## Contents
- `SPEC.md`: the v0 spec in plain English, with examples
- `schemas/`: JSON Schemas (draft 2020-12) for the 6 messages and 3 category extensions (hotel, electronics, b2b)
- `demo/haggle_demo.py`: one shopper agent and two seller agents with private floor prices, haggling a hotel stay and a laptop
- `demo/sample_transcript.txt`: output from a real run with `--recording` (seller floors and shopper ceilings are never printed; run without the flag locally to see them)

## Run
```
pip install cryptography   # jsonschema optional; a built-in checker is used if absent
python3 demo/haggle_demo.py
```
The agents are rule-based and need no API keys. Every message is checked against its schema, offers and counters are signed with Ed25519, and nonces and expiry are enforced. The demo also shows that a replayed message, a tampered price and an expired offer are all rejected.

Status: draft v0.

## License
Code and schemas: Apache-2.0 (`LICENSE`). Spec text: CC-BY-4.0 (`LICENSE-docs`). Patent non-assert: `PATENTS.md`. See `NOTICE`.

