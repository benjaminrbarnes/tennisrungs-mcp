import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tennisrungs_mcp.workflow_api import plan, reconcile_local
from tennisrungs_mcp.workflow import Intent, Observation, reconcile
from tennisrungs_mcp.journal import Journal
from tennisrungs_mcp.models import SafetyError


def example():
    return json.loads((Path(__file__).parents[1] / "examples/workflow.json").read_text())


def test_offline_plan_preserves_explicit_guard_and_stable_hash():
    p = example()
    r = plan(**p)
    assert r["decision"]["action"] == "WAIT"
    assert r["guard_utc"] == "2030-01-02T13:30:00+00:00"
    assert r["guard_policy"] == "explicit_preserved"
    assert r == plan(**p)
    assert not r["live_execution_enabled"] and not r["authority_verified"] and not r["timer_installed"]
    changed = copy.deepcopy(p)
    changed["intent"]["cap_cents"] = 1501
    assert plan(**changed)["intent_hash"] != r["intent_hash"]


def test_missing_source_assertions_refresh_not_commit():
    p = example(); p["observation"] = {}
    assert plan(**p)["decision"]["action"] == "REFRESH"


def test_input_claim_of_atomic_withdrawal_never_enables_it():
    p = example()
    p["intent"]["can_withdraw"] = True
    p["observation"]["withdrawal_atomic"] = True
    p["now"] = p["intent"]["deadline_guard"]
    assert plan(**p)["decision"]["action"] == "REVIEW_WITHDRAWAL"


def test_late_acceptance_never_produces_withdrawal():
    p = example(); p["observation"]["match_state"] = "ACCEPTED"
    p["now"] = "2030-01-02T09:30:00-05:00"
    assert plan(**p)["decision"]["action"] == "BLOCK"


def test_journal_reconciliation_is_readonly_and_unknown_blocks(tmp_path):
    file = tmp_path / "operations.sqlite3"
    j = Journal(file); j.begin("synthetic", "accept", {"challenge_id": 303}); j.finish("synthetic", "UNKNOWN"); j.close()
    before = hashlib.sha256(file.read_bytes()).hexdigest()
    r = reconcile_local(**example(), journal_path=file, operation_key="synthetic")
    assert r["decision"]["action"] == "RECONCILE_UNKNOWN"
    assert r["journal_modified"] is False
    assert hashlib.sha256(file.read_bytes()).hexdigest() == before


def test_missing_journal_is_not_created(tmp_path):
    file = tmp_path / "missing" / "operations.sqlite3"
    with pytest.raises(SafetyError):
        reconcile_local(**example(), journal_path=file, operation_key="synthetic")
    assert not file.exists() and not file.parent.exists()


def test_verified_local_record_does_not_invent_fresh_source(tmp_path):
    file = tmp_path / "operations.sqlite3"
    j = Journal(file); j.begin("synthetic", "accept", {"challenge_id": 303}); j.finish("synthetic", "VERIFIED"); j.close()
    assert reconcile_local(**example(), journal_path=file, operation_key="synthetic")["decision"]["action"] == "REFRESH"


def test_cli_offline_commands_do_not_initialize_credentials_or_live_runtime(monkeypatch, capsys):
    from tennisrungs_mcp import cli
    monkeypatch.setattr(cli, "runtime", lambda **_: pytest.fail("must not initialize live runtime"))
    file = Path(__file__).parents[1] / "examples/workflow.json"
    assert cli.main(["--keychain", "--enable-writes", "workflow", "plan", "--input", str(file)]) == 0
    assert json.loads(capsys.readouterr().out)["live_execution_enabled"] is False


def test_wall_clock_fold_interval_uses_elapsed_utc():
    i = Intent("synthetic", datetime.fromisoformat("2030-11-03T01:30:00-04:00"), datetime.fromisoformat("2030-11-03T01:30:00-05:00"), "synthetic-court")
    o = Observation(fresh=True, complete=True, exact_match=True)
    assert reconcile(i, o, datetime(2030, 10, 29, tzinfo=timezone.utc)).action == "REVIEW"


@pytest.mark.parametrize("field,value", [("can_book", "false"), ("cap_cents", True), ("ladder_id", True)])
def test_invalid_types_not_coerced_to_authority_or_money(field, value):
    p = example(); p["intent"][field] = value
    with pytest.raises((SafetyError, ValueError)):
        plan(**p)
