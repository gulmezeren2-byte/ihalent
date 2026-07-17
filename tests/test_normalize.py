from ihalent.normalize import display_name, normalize_company


def test_folds_case_and_diacritics() -> None:
    assert normalize_company("ABC İNŞAAT") == normalize_company("abc insaat")


def test_strips_legal_suffixes() -> None:
    a = normalize_company("ACME İNŞAAT SANAYİ VE TİCARET LİMİTED ŞİRKETİ")
    b = normalize_company("ACME İNŞAAT")
    assert a == b == "acme insaat"


def test_ltd_sti_variants_fold() -> None:
    assert normalize_company("X YAPI LTD. ŞTİ.") == normalize_company("X YAPI LTD STI")


def test_does_not_overmerge_distinct_firms() -> None:
    assert normalize_company("ANADOLU İNŞAAT") != normalize_company("ANKARA İNŞAAT")


def test_idempotent() -> None:
    once = normalize_company("Örnek İnşaat A.Ş.")
    assert normalize_company(once) == once


def test_display_name_prefers_fullest() -> None:
    variants = ["ACME", "ACME İNŞAAT LTD ŞTİ", "ACME İNŞAAT"]
    assert display_name(variants) == "ACME İNŞAAT LTD ŞTİ"
