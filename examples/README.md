# Example: four real December-2025 awards

The `notices/` folder holds four real result notices (Sonuç İlanı), pulled from EKAP via
ihale-mcp, one per file, named by İKN. They span four kinds of awarding authority on
purpose:

| İKN | authority | discount | note |
|---|---|---|---|
| 2025/2337797 | Ağrı İl Özel İdaresi | 19.99% | joint venture, provincial repair job |
| 2025/2198370 | DSİ 14. Bölge Müdürlüğü | 33.87% | 12 valid bids — real competition |
| 2025/2174700 | Esenler Belediyesi | 21.99% | municipal school/mosque repairs |
| 2025/2388267 | İstanbul Üniversitesi-Cerrahpaşa | **-2.96%** | emergency "pazarlık", awarded *above* estimate |

We ship the notices, not a redistributed dataset. `build_sample.py` parses them into
`sample-awards.jsonl` exactly as `ihalent ingest` would with your own collected notices:

```
python build_sample.py
ihalent overview   sample-awards.jsonl
ihalent discounts  sample-awards.jsonl --by authority
```

The `-2.96%` case is the one to notice. A contract signed 2.96% above the public estimate,
through an emergency procedure that skips open bidding, is exactly the kind of thing these
notices disclose and nobody aggregates — which is the whole reason this tool exists.
