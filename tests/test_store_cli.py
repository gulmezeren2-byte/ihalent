import json
from pathlib import Path

from typer.testing import CliRunner

from ihalent.cli import app
from ihalent.model import Award, TenderType
from ihalent.store import dump_awards, load_awards

runner = CliRunner()


def sample_awards() -> list[Award]:
    return [
        Award(ikn="2025/1", authority="A", winner="ACME LTD",
              winners_all=["ACME LTD"], estimate_try=1000.0, contract_try=800.0,
              valid_bid_count=4, tender_type=TenderType.WORKS),
        Award(ikn="2025/2", authority="B", winner="BETA AŞ",
              winners_all=["BETA AŞ"], estimate_try=2000.0, contract_try=1900.0,
              valid_bid_count=1, tender_type=TenderType.SERVICE),
    ]


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "awards.jsonl"
    assert dump_awards(sample_awards(), path) == 2
    loaded = load_awards(path)
    assert {a.ikn for a in loaded} == {"2025/1", "2025/2"}
    assert loaded[0].discount_pct == 20.0


def test_dedupe_last_wins(tmp_path: Path) -> None:
    path = tmp_path / "dupes.jsonl"
    path.write_text(
        json.dumps({"ikn": "2025/1", "contract_try": 100.0}) + "\n"
        + json.dumps({"ikn": "2025/1", "contract_try": 200.0}) + "\n",
        encoding="utf-8",
    )
    loaded = load_awards(path)
    assert len(loaded) == 1
    assert loaded[0].contract_try == 200.0


def test_load_bad_json_names_the_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text('{"ikn": "2025/1"}\nnot json\n', encoding="utf-8")
    try:
        load_awards(path)
    except ValueError as exc:
        assert ":2:" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_cli_overview(tmp_path: Path) -> None:
    path = tmp_path / "awards.jsonl"
    dump_awards(sample_awards(), path)
    result = runner.invoke(app, ["overview", str(path)])
    assert result.exit_code == 0
    assert "awarded" in result.output


def test_cli_overview_json(tmp_path: Path) -> None:
    path = tmp_path / "awards.jsonl"
    dump_awards(sample_awards(), path)
    result = runner.invoke(app, ["overview", str(path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["awarded"] == 2
    assert payload["data_gaps"]["missing_estimate"] == 0


def test_cli_firm(tmp_path: Path) -> None:
    path = tmp_path / "awards.jsonl"
    dump_awards(sample_awards(), path)
    result = runner.invoke(app, ["firm", str(path), "ACME"])
    assert result.exit_code == 0
    assert "ACME" in result.output


def test_cli_firm_not_found(tmp_path: Path) -> None:
    path = tmp_path / "awards.jsonl"
    dump_awards(sample_awards(), path)
    result = runner.invoke(app, ["firm", str(path), "NOBODY"])
    assert result.exit_code == 1


def test_cli_discounts_json(tmp_path: Path) -> None:
    path = tmp_path / "awards.jsonl"
    dump_awards(sample_awards(), path)
    result = runner.invoke(app, ["discounts", str(path), "--by", "authority", "--json"])
    assert result.exit_code == 0
    groups = json.loads(result.output)
    assert {g["label"] for g in groups} == {"A", "B"}


def test_cli_missing_file(tmp_path: Path) -> None:
    result = runner.invoke(app, ["overview", str(tmp_path / "nope.jsonl")])
    assert result.exit_code == 2


def test_cli_ingest(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "announcements": [
                    {
                        "type": {"code": "4", "description": "Sonuç İlanı"},
                        "markdown_content": (
                            "**SONUÇ İLANI** 2025/1234567\n"
                            "| Yaklaşık Maliyeti | : | 1.000.000,00 TRY |\n"
                            "| Bedeli | : | 800.000,00 TRY |\n"
                            "| Yüklenicisi | : | Z LTD |\n"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "awards.jsonl"
    result = runner.invoke(app, ["ingest", str(bundle), "-o", str(out)])
    assert result.exit_code == 0
    loaded = load_awards(out)
    assert loaded[0].discount_pct == 20.0


def test_cli_ingest_no_result_notice(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.json"
    bundle.write_text(
        json.dumps({"announcements": [{"type": {"code": "1"}, "markdown_content": "x"}]}),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["ingest", str(bundle), "-o", str(tmp_path / "a.jsonl")])
    assert result.exit_code == 1


def test_cli_single_bid(tmp_path: Path) -> None:
    path = tmp_path / "awards.jsonl"
    dump_awards(sample_awards(), path)
    result = runner.invoke(app, ["single-bid", str(path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["with_known_bid_count"] == 2
    assert payload["single_bid_count"] == 1  # BETA AŞ has a single valid bid
    assert payload["awards"][0]["winner"] == "BETA AŞ"


def test_cli_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "ihalent" in result.output
