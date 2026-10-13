import json
from datetime import date

import pytest

from tennisrungs_mcp.iparcs_consumer import ConsumerAdapter, BoundaryError, PublicTransport, covers
from tennisrungs_mcp.iparcs_reads import IParcsReads
from test_iparcs_consumer import Fake, day, slot, envelope


def test_empty_search_page_before_total_never_returns_partial():
    f = Fake([envelope({"items": [{"id": 1}], "total": 2, "next_start_index": 20}),
              envelope({"items": [], "total": 2, "next_start_index": 40})])
    with pytest.raises(BoundaryError, match="coverage"):
        ConsumerAdapter(f).search("synthetic")


def test_wrong_resource_calendar_fails_closed():
    f = Fake([envelope({"details": {"resource_id": 999, "daily_details": [day()]}})])
    with pytest.raises(BoundaryError, match="court"):
        ConsumerAdapter(f).availability(1, date(2030, 1, 1), date(2030, 1, 1))


def test_whole_block_result_is_not_booking():
    f = Fake([envelope({"details": {"resource_id": 1, "daily_details": [day([slot("06:00:00", "23:00:00")])]}})])
    r = IParcsReads(ConsumerAdapter(f)).check_slot(1, "2030-01-01", "09:30:00", "11:30:00")
    assert r.rows[0]["whole_block_available"] is True
    assert "not a hold or booking" in r.warnings[0]


def test_cli_iparcs_never_accesses_tennisrungs_keychain(monkeypatch, capsys):
    from tennisrungs_mcp import cli
    monkeypatch.setattr(cli, "runtime", lambda **_: pytest.fail("must not initialize TennisRungs session"))
    monkeypatch.setattr(IParcsReads, "search", lambda _, keyword: IParcsReads().result("/synthetic", [{"id": 1}]))
    assert cli.main(["--keychain", "iparcs", "search", "synthetic"]) == 0
    assert json.loads(capsys.readouterr().out)["rows"] == [{"id": 1}]


def test_public_transport_rejects_checkout_commit():
    with pytest.raises(BoundaryError):
        PublicTransport().request("POST", "/rest/checkout/order/commit", {})


@pytest.mark.parametrize("field,value", [("check_in_only", True), ("status", True)])
def test_overnight_flags_and_wrong_status_type_not_available(field, value):
    d = day([slot("06:00:00", "23:00:00")])
    d[field] = value
    assert not covers(d, "09:30:00", "11:30:00")


def test_string_false_available_not_truthy():
    d = day([slot("06:00:00", "23:00:00", available="false")])
    assert not covers(d, "09:30:00", "11:30:00")


def test_fractional_seconds_not_supported():
    assert not covers(day([slot("06:00:00", "23:00:00")]), "09:30:00.5", "11:30:00")


def test_missing_detail_not_complete_success():
    with pytest.raises(BoundaryError, match="unavailable"):
        ConsumerAdapter(Fake([envelope({})])).detail(1)


def test_malformed_result_code_not_exposed_in_error():
    from tennisrungs_mcp.iparcs_consumer import unwrap
    with pytest.raises(BoundaryError) as e:
        unwrap(envelope({}, "private-response-marker"))
    assert "private-response-marker" not in str(e.value)
