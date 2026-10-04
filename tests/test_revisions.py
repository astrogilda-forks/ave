import json

import pytest

from scripts import validate_records

SCHEMA = json.loads(validate_records.SCHEMA_PATH.read_text(encoding="utf-8"))
KNOWN = set(SCHEMA["properties"])


def entry(**overrides):
    base = {
        "date": "2026-09-28T23:51:58Z",
        "field": "verification_basis",
        "from": "artifact_reconstructed",
        "to": "substrate_reconstructed",
        "reason_code": "declaration_added",
        "reason": "evidence_vantage stated as substrate.",
    }
    base.update(overrides)
    return base


def substrate_record(revisions):
    """A record whose derived basis is substrate_reconstructed, so the default
    entry above ends where the record stands."""
    return {
        "evidence_vantage": "substrate",
        "evidence_basis_engines": ["pattern", "external_authority"],
        "revisions": revisions,
    }


def schema_errors(revisions):
    validator = validate_records.build_validator(SCHEMA)
    errors = validator.iter_errors({"revisions": revisions})
    return [e.message for e in errors if list(e.absolute_path)[:1] == ["revisions"]]


def test_an_entry_ending_at_the_derived_value_passes():
    assert validate_records.check_revisions(substrate_record([entry()]), KNOWN) == []


def test_a_derived_field_is_checked_against_the_derivation_not_a_stored_value():
    # The record stores no verification_basis at all; the entry still has to
    # match what a consumer derives from it.
    record = substrate_record([entry()])
    assert "verification_basis" not in record
    record["evidence_vantage"] = "artifact"
    errors = validate_records.check_revisions(record, KNOWN)
    assert any("reads 'artifact_reconstructed' today" in e for e in errors)


def test_a_stored_field_is_checked_against_the_record():
    record = substrate_record([entry(field="evidence_vantage", **{"from": None, "to": "artifact"})])
    errors = validate_records.check_revisions(record, KNOWN)
    assert any("reads 'substrate' today" in e for e in errors)


def test_entries_for_one_field_must_chain():
    first = entry(**{"from": None, "to": "artifact_intercepted"}, date="2026-09-01T00:00:00Z")
    errors = validate_records.check_revisions(substrate_record([first, entry()]), KNOWN)
    assert any("next entry starts from 'artifact_reconstructed'" in e for e in errors)


def test_a_chained_history_passes():
    first = entry(**{"from": None, "to": "artifact_reconstructed"}, date="2026-09-01T00:00:00Z")
    assert validate_records.check_revisions(substrate_record([first, entry()]), KNOWN) == []


def test_an_entry_that_changes_nothing_is_refused():
    same = entry(**{"from": "substrate_reconstructed"})
    errors = validate_records.check_revisions(substrate_record([same]), KNOWN)
    assert any("records no change" in e for e in errors)


def test_entries_must_be_oldest_first():
    later = entry(field="evidence_vantage", **{"from": None, "to": "substrate"}, date="2026-09-29T00:00:00Z")
    errors = validate_records.check_revisions(substrate_record([later, entry()]), KNOWN)
    assert "revisions: entries are not oldest first" in errors


@pytest.mark.parametrize("field", ["no_such_field", "revisions"])
def test_an_entry_must_name_a_record_field(field):
    errors = validate_records.check_revisions(substrate_record([entry(field=field)]), KNOWN)
    assert errors == [f"revisions: '{field}' is not a record field"]


@pytest.mark.parametrize("bad", [None, "text", [None, "x", {"field": 3}]])
def test_a_malformed_history_is_left_to_the_schema(bad):
    assert validate_records.check_revisions({"revisions": bad}, KNOWN) == []


def test_the_schema_refuses_a_code_outside_the_closed_set():
    assert schema_errors([entry(reason_code="added evidence_vantage")])


def test_the_schema_refuses_an_entry_without_a_reason():
    incomplete = entry()
    del incomplete["reason"]
    assert schema_errors([incomplete])


def test_the_schema_refuses_an_empty_history():
    assert schema_errors([])


def test_the_schema_accepts_a_complete_entry():
    assert schema_errors([entry()]) == []


def test_every_published_history_chains_to_its_record():
    paths = sorted(validate_records.RECORDS_DIR.glob("AVE-*.json"))
    problems = []
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        problems += [f"{path.name}: {e}" for e in validate_records.check_revisions(record, KNOWN)]
    assert paths and problems == []


def test_the_validator_fails_a_record_whose_history_disagrees_with_it(tmp_path, monkeypatch):
    record = json.loads((validate_records.RECORDS_DIR / "AVE-2026-00074.json").read_text(encoding="utf-8"))
    record["revisions"] = [entry(**{"from": None, "to": "artifact_reconstructed"})]
    (tmp_path / "records").mkdir()
    (tmp_path / "schema").mkdir()
    (tmp_path / "records" / "AVE-2026-00074.json").write_text(json.dumps(record), encoding="utf-8")
    (tmp_path / validate_records.SCHEMA_PATH).write_text(json.dumps(SCHEMA), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert validate_records.main() == 1
