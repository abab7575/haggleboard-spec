# HaggleBoard Protocol (HBP), v0 draft

HBP lets a **buyer agent** and a **seller agent** agree a price and terms for anything. It defines only the conversation. Discovery, transport and payment use existing standards:

| Layer | Use |
|---|---|
| Find the seller | `/.well-known/haggleboard` (alongside UCP's `/.well-known/ucp`) |
| Carry messages | HTTPS POST, A2A task messages, or an MCP tool call |
| **Agree price and terms** | **HBP (this spec)** |
| Pay and fulfil | UCP checkout, ACP `/checkout_sessions`, a purchase order, or a plain URL |

**Two rules that never change:**
1. **HBP never touches money.** No card data, no balances and no fees. A deal ends in a signed *deal token* that the buyer takes to the seller's own checkout.
2. **Floors stay private.** No message reveals a reserve price. Agents disclose only the offers they choose to make.

## 1. Messages

| Type | Sent by | Meaning | Signed? |
|---|---|---|---|
| `request` | buyer | "I need X." Category, item details, optional budget cap, deadline, round cap | optional |
| `offer` | seller | Firm terms, binding until `expires_at` | **required** |
| `counter` | either side | New terms in reply to an offer or counter | **required** |
| `accept` | either side | Locks the exact terms of the referenced message | **required** |
| `decline` | either side | Ends the thread (`price`, `terms`, `withdrawn`, `other`) | optional |
| `expire` | either side or relay | Records that a deadline or the round cap has passed | optional |

A thread runs: `request → offer → (counter ↔ counter)* → accept | decline | expire`.

## 2. Required fields (every message)

| Field | Meaning |
|---|---|
| `hbp` | Protocol version, `"0.1"` |
| `type` | One of the six types |
| `thread_id` | Same for every message in one negotiation |
| `message_id` | Unique per message |
| `in_reply_to` | The `message_id` being answered (all except `request`) |
| `sent_at` | RFC 3339 UTC time |
| `from` | `{agent_id, role}`. `agent_id` is a `did:web` or an https domain that publishes its public key |
| `nonce` | At least 16 random characters, used once per agent. Receivers reject repeats |
| `signature` | `{alg:"Ed25519", key_id, value}` over the canonical JSON of the message minus `signature` (sorted keys, no whitespace) |

Offers and counters add `terms` (`category`, `item`, `price{amount, currency}`, optional `extensions`), `round` and `expires_at`. Amounts are decimal strings, such as `"199.00"`, and never floats.

## 3. What every receiver checks
1. The message validates against `schemas/<type>.json` and the category extension.
2. `expires_at` has not passed.
3. The signature verifies against the sender's published key.
4. The `(agent_id, nonce)` pair has not been seen before.
5. `round` does not exceed the request's `max_rounds`.

If any check fails, the receiver drops the message and does not reply.

## 4. Example: hotel

```json
{"hbp":"0.1","type":"request","thread_id":"t_8f2a","message_id":"m_01",
 "sent_at":"2026-10-24T12:00:00Z","from":{"agent_id":"did:web:shopper.example","role":"buyer"},
 "nonce":"4c1e9a0b7d2f6e5a3b8c","expires_at":"2026-10-24T12:30:00Z","max_rounds":6,
 "need":{"category":"hotel","quantity":1,"item":{"property_id":"harbourhotel-dub-01",
   "check_in":"2026-11-13","check_out":"2026-11-15","room_type":"double","guests":2,
   "cancellation":"free_until_24h","breakfast":true}}}
```
```json
{"hbp":"0.1","type":"counter","thread_id":"t_8f2a","message_id":"m_09","in_reply_to":"m_08",
 "sent_at":"2026-10-24T12:00:18Z","from":{"agent_id":"did:web:harbourhotel.example","role":"seller"},
 "nonce":"9d0c…","round":5,"expires_at":"2026-10-24T12:10:18Z",
 "terms":{"category":"hotel","item":{…},"price":{"amount":"199.00","currency":"EUR"}},
 "signature":{"alg":"Ed25519","key_id":"did:web:harbourhotel.example#k1","value":"…"}}
```

## 5. Accept and the checkout handoff
An `accept` names the `accepted_message_id` and the `terms_hash` (the sha256 of the canonical `terms`). It also carries a **deal token** signed by the seller:

```json
"deal_token":{"terms":{…},"terms_hash":"96bc5f19…","valid_until":"2026-10-24T12:15:20Z",
  "handoff":{"protocol":"ucp","endpoint":"https://harbourhotel.example/.well-known/ucp"},
  "seller_signature":{"alg":"Ed25519","key_id":"…#k1","value":"…"}}
```
- **UCP:** the buyer opens a checkout and attaches the deal token as line-item pricing evidence. The seller checks its own signature and the `terms_hash`, then prices the cart at the agreed amount.
- **ACP:** the buyer calls `POST /checkout_sessions` with the deal token in metadata. The seller does the same check, then sets the price.
- **B2B:** the deal token becomes the reference on a purchase order.

Payment authorisation (AP2 mandates, Stripe and the like) happens entirely in those systems. HBP's role ends at the handoff.

## 6. Category extensions (`terms.item`)
| Category | Required | Optional, negotiable |
|---|---|---|
| `hotel` | property_id, check_in, check_out, room_type, guests | cancellation, breakfast |
| `electronics` | gtin, condition (new / open_box / refurbished) | warranty_months, shipping_days, returns_days |
| `b2b` | sku, quantity | volume_tiers, payment_terms_days, contract_months, delivery_sla_days |

New categories are added as new `ext-*.json` files. The core does not change.

## 7. Open for v0.2
- Multi-seller auctions (one request sent to many sellers)
- Bundles
- Key rotation and revocation
- Agent reputation
- A rule-of-thumb guard against collusive price signalling
- Making relay or registry operators optional and neutral
