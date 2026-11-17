# Data model and JSON schema

ihalent's interchange format is JSON Lines: one award per line. This page documents the
`Award` record so you can produce it from any source, not only ihale-mcp.

## Award

| field | type | meaning |
|---|---|---|
| `ikn` | string | İhale Kayıt Numarası, e.g. `"2025/2198370"`, kept as printed (some carry a suffix: `"2026/1007522-4"`). The primary key. |
| `title` | string \| null | Tender title. |
| `authority` | string \| null | Awarding authority (idare). |
| `province` | string \| null | Province. |
| `tender_type` | string | `mal` \| `yapim` \| `hizmet` \| `danismanlik` \| `unknown`. |
| `estimate_try` | number \| null | Yaklaşık Maliyeti (public estimate), nominal lira; the lira figure when a foreign one is printed beside it. `null` also when the notice states there is none ("- TRY"). |
| `contract_try` | number \| null | Sözleşme Bedeli (contract price), nominal lira. `null` when the bulletin prices the contract in another currency: no exchange rate is guessed. |
| `winner` | string \| null | Lead bidder (first named party in a joint venture). |
| `winners_all` | string[] | All named parties (the JV members). |
| `is_joint_venture` | bool | True if the award went to an İş Ortaklığı. |
| `downloaders` | int \| null | Firms that downloaded the documents. |
| `bid_count` | int \| null | Toplam Teklif Sayısı. |
| `valid_bid_count` | int \| null | Toplam Geçerli Teklif Sayısı. |
| `result_date` | string \| null | Contract date, ISO (`YYYY-MM-DD`) where parseable. |
| `cancelled` | bool | True for a cancelled tender (result notice with no winner/price). |
| `lot_count` | int | How many per-lot notices (kısmi teklif) were merged into this record; 1 otherwise. |
| `lots_unverified` | bool | True when the record is built from per-lot notices with no proof that every lot is in it (the bulletin prints lots on different days). `discount_pct` is then `null`. Defaults to `false`. |
| `lots` | object[] | One entry per lot when several lot notices were merged, else empty: `winners` (string[], lead first), `contract_try` (number \| null), `is_joint_venture` (bool). `winner` / `winners_all` then name every lot's winners; firm totals credit each firm only its own lots. Defaults to `[]`. |

Two fields are **computed** and appear in serialized output but are never stored as input:

| field | type | meaning |
|---|---|---|
| `discount_pct` | number \| null | `100 * (estimate - contract) / estimate`, rounded to 2 dp. `null` if either value is missing, the estimate is 0, or `lots_unverified` is true. Negative means the contract came in *above* estimate. |
| `single_bid` | bool \| null | `valid_bid_count <= 1`. `null` if the count is missing. |

### The null discipline

Every optional field is `null` when the source did not carry it — never `0`, never `""`.
A discount computed from a missing estimate is `null`, not `0%`. This is load-bearing: the
analytics layer counts these gaps and reports them (`data_gaps` in the overview, the
`coverage` block on every statistic), so a mean is always qualified by how many records
actually had the number.

## Example line

```json
{"ikn": "2025/2198370", "title": "İSTANBUL ARNAVUTKÖY TÜRKKÖŞE DERESİ ISLAHI", "authority": "DSİ 14. Bölge Müdürlüğü", "province": "İstanbul", "tender_type": "yapim", "estimate_try": 29802943.48, "contract_try": 19709997.4, "winner": "Ö. Y.", "winners_all": ["Ö. Y.", "ATAŞ MÜHENDİSLİK ..."], "is_joint_venture": true, "downloaders": 34, "bid_count": 20, "valid_bid_count": 12, "result_date": "2026-02-13", "cancelled": false, "discount_pct": 33.87, "single_bid": false}
```

## Producing awards

Three routes, all landing on the same JSONL:

1. **From ihale-mcp / EKAP** — `ihalent ingest bundle.json` (or `ihalent.ingest_bundle` in
   Python). Accepts a `get_tender_announcements` object, a list of them, or a list of
   `{tender, announcements}` pairs.
2. **From a single notice** — `ihalent parse notice.md` emits one record you can append.
3. **From your own pipeline** — build `Award` objects directly and `dump_awards(...)`; only
   `ikn` is required.

## Company-name folding

Firm queries and JV membership are matched on a normalized key: Turkish diacritics folded to
ASCII, legal-form suffixes (`LİMİTED ŞİRKETİ`, `LTD ŞTİ`, `SANAYİ VE TİCARET ...`) stripped,
whitespace and punctuation collapsed. The fold is deliberately conservative — it will not
merge `ANADOLU İNŞAAT` with `ANKARA İNŞAAT` — and `firm` reports `distinct_spellings` so an
over-broad query is visible rather than silently merging unrelated companies.
