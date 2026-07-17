"""Fixtures built from real EKAP result notices.

The two markdown blobs below are the exact result-notice bodies EKAP served
for two real tenders (an İl Özel İdare repair job and a DSİ stream works),
trimmed to the tables the parser reads. Testing against the real template —
not a tidied-up invention — is the point: if EKAP's rendering is what these
tests encode, then green tests mean the parser handles the real thing.
"""

from __future__ import annotations

import pytest

# İKN 2025/2337797 — award, joint venture, discount ~19.99%
NOTICE_AWARD_JV = """**SONUÇ İLANI****BİNA ONARIMI YAPTIRILACAKTIR**

| **İhale kayıt numarası** | **:** | **2025/2337797** |
| **d)** Yaklaşık Maliyeti | : | 2.783.270,09 TRY |
| **a)** Dokümanı EKAP üzerinden e-imza kullanarak indiren sayısı | : | 8 |
| **b)** Toplam Teklif Sayısı | : | 4 |
| **c)** Toplam Geçerli Teklif Sayısı | : | 3 |
| **a)** Tarihi | : | 26.01.2026 |
| **b)** Bedeli | : | 2.227.000,00 TRY |
| **d)** Yüklenicisi | : | MUHAMMED HANEFİ YILDIRIM, BEDKURT GIDA İNŞAAT OTOMOTİV LİMİTED ŞİRKETİ İş Ortaklığı |
"""

# İKN 2025/2198370 — award, single firm named first, discount ~33.87%
NOTICE_AWARD_BIG = """**SONUÇ İLANI****DERE ISLAHI YAPTIRILACAKTIR**

| **İhale kayıt numarası** | **:** | **2025/2198370** |
| **d)** Yaklaşık Maliyeti | : | 29.802.943,48 TRY |
| **a)** Dokümanı EKAP üzerinden e-imza kullanarak indiren sayısı | : | 34 |
| **b)** Toplam Teklif Sayısı | : | 20 |
| **c)** Toplam Geçerli Teklif Sayısı | : | 12 |
| **b)** Bedeli | : | 19.709.997,40 TRY |
| **d)** Yüklenicisi | : | ÖZDEN YEL, ATAŞ MÜHENDİSLİK İNŞAAT SANAYİ VE TİCARET LİMİTED ŞİRKETİ İş Ortaklığı |
"""

# A cancelled tender: result notice with no winner and no contract value.
NOTICE_CANCELLED = """**SONUÇ İLANI****İPTAL**

| **İhale kayıt numarası** | **:** | **2025/2500001** |
| **d)** Yaklaşık Maliyeti | : | 1.000.000,00 TRY |
| İhale iptal edilmiştir. | | |
"""


@pytest.fixture()
def notice_award_jv() -> str:
    return NOTICE_AWARD_JV


@pytest.fixture()
def notice_award_big() -> str:
    return NOTICE_AWARD_BIG


@pytest.fixture()
def notice_cancelled() -> str:
    return NOTICE_CANCELLED
