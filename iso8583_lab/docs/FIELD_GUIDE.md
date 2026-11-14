# Field Guide for the Included Examples

ISO 8583 field meanings are profile-specific. The table below describes the
educational profile in this repository, not a promise about every acquirer,
processor, or card network.

| Key | Common name | What this lab does with it |
|---|---|---|
| `t` | Message Type Indicator | Chooses the transaction class and server rule file |
| `p` | Primary bitmap | Generated automatically; signals fields 1–64 |
| `1` | Secondary bitmap | Generated automatically when a field above 64 exists |
| `2` | PAN | Used for Luhn validation and authorization decisions |
| `3` | Processing code | Echoed in transaction responses |
| `4` | Transaction amount | Fixed-width minor-unit amount, such as `000000002500` |
| `7` | Transmission date/time | Generated as `MMDDhhmmss`; checked against server time |
| `11` | STAN | Six-digit trace number; captured across the three-leg flow |
| `12` | Local transaction time | Generated as `hhmmss`; checked against server time |
| `13` | Local transaction date | Generated as `MMDD`; checked against server date |
| `37` | Retrieval reference number | Correlation value reused by the confirmation |
| `39` | Response code | Carries the lab's approval or rejection result |
| `41` | Terminal ID | Identifies the sample terminal |
| `42` | Merchant/acceptor ID | Identifies the sample merchant |
| `44` | Additional response data | Lab-readable text such as `PAN4=1111,STAN=100001` |
| `49` | Currency code | Sample numeric currency identifier |
| `60` | Reserved national | Carries the lab's administrative parameter-status request |
| `70` | Network management information code | `001` requests network sign-on and forces a secondary bitmap |
| `90` | Original data elements | Used by reversal and forces a secondary bitmap |

## MTIs in this lab

| Request | Response | Scenario |
|---|---|---|
| `0100` | `0110` | Authorization |
| `0120` | none | Final authorization confirmation in the three-leg demo |
| `0200` | `0210` | Financial transaction |
| `0220` | `0230` | Financial advice/acknowledgement |
| `0400` | `0410` | Reversal request/response |
| `0420` | `0430` | Reversal advice/response |
| `0600` | `0610` | Administrative request/response |
| `0800` | `0810` | Network-management sign-on/response using DE70 |
| `0800` | none | Separate one-way network-management demonstration without DE70 |

The no-response choices are deliberate lab behavior. A real profile may define
different semantics and response requirements.

The two reversal forms deliberately use separate response templates. This is
slightly repetitive, but makes the `0400 → 0410` and `0420 → 0430` mappings
visible without requiring students to inspect a compound substitution.

## Response codes in this lab

| DE39 | Meaning here |
|---|---|
| `00` | Approved |
| `05` | Business decline for the configured PAN pattern |
| `14` | Invalid PAN/Luhn failure |
| `30` | Invalid or stale date/time |
| `96` | Default system/configuration rejection |

These are common-looking values, but the processor's documentation is always
the authority for production behavior.

## Why DE44 says `PAN4`

The approval response uses:

```text
PAN4=1111,STAN=100001
```

`PAN4` makes it clear that only the last four digits are present. This text is
an intentionally readable classroom payload, not a universal definition of
DE44.

## Why DE90 creates two bitmaps

The primary bitmap covers fields 1 through 64. DE90 is above 64, so bit 1 of
the primary bitmap announces a secondary bitmap. The secondary bitmap then
marks DE90 as present. The encoder handles both automatically; the message JSON
only needs field `"90"`.
