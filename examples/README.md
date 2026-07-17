# Example: nine real December-2025 awards

Two real sources, both collected from EKAP via ihale-mcp, shipped as-is (we ship the
collected data, not a redistributed dataset). `build_sample.py` turns them into
`sample-awards.jsonl` — exactly the path a user takes with their own collected data:

```
python build_sample.py
ihalent overview   sample-awards.jsonl
ihalent discounts  sample-awards.jsonl --by authority
ihalent single-bid sample-awards.jsonl
```

**`notices/`** — four loose result notices (Sonuç İlanı), one per file, named by İKN,
spanning four kinds of authority:

| İKN | authority | discount | note |
|---|---|---|---|
| 2025/2337797 | Ağrı İl Özel İdaresi | 19.99% | joint venture, provincial repair job |
| 2025/2198370 | DSİ 14. Bölge Müdürlüğü | 33.87% | 12 valid bids — real competition |
| 2025/2174700 | Esenler Belediyesi | 21.99% | municipal school/mosque repairs |
| 2025/2388267 | İstanbul Üniversitesi-Cerrahpaşa | **-2.96%** | emergency "pazarlık", awarded *above* estimate |

**`istanbul-yapim-2025.json`** — an ihale-mcp bundle of six İstanbul construction tenders
(two municipalities, a state bank, the provincial investment office, a university, the water
utility), fed through ihalent's own `ingest`. Together with the notices, deduplicated by
İKN, that is nine awards spanning discounts from **-2.96% to +33.87%**.

The `-2.96%` case is the one to notice. A contract signed 2.96% above the public estimate,
through an emergency procedure that skips open bidding, is exactly the kind of thing these
notices disclose and nobody aggregates — which is the whole reason this tool exists.
