import copy
import json

import pytest

from scripts import validate_records


def _validator():
    schema = json.loads(validate_records.SCHEMA_PATH.read_text(encoding="utf-8"))
    return validate_records.build_validator(schema)


BASE = {
    "ave_id": "AVE-2026-99999",
    "schema_version": "1.1.0",
    "status": "draft",
    "title": "Revisions fixture",
    "description": "A minimal draft record carrying a revisions array.",
    "attack_class": "test",
    "behavioral_fingerprint": "test",
    "references": ["https://example.com"],
    "last_updated": "2026-09-28T23:51:58Z",
    "revisions": [
        {
            "date": "2026-09-28",
            "field": "evidence_vantage",
            "from": None,
            "to": "substrate",
            "reason_code": "declaration_added",
        }
    ],
}


def _record(**entry_changes):
    record = copy.deepcopy(BASE)
    record["revisions"][0].update(entry_changes)
    return record


def test_an_added_field_entry_with_null_from_is_valid():
    assert validate_records.check_schema(_record(), _validator()) == []
    assert validate_records.check_revisions_append_only(_record()) == []


def test_an_unregistered_reason_code_is_refused():
    errors = validate_records.check_schema(_record(reason_code="value_tweaked"), _validator())
    assert any("value_tweaked" in error for error in errors)


@pytest.mark.parametrize("missing", ["date", "field", "from", "to", "reason_code"])
def test_every_required_entry_member_is_required(missing):
    record = _record()
    del record["revisions"][0][missing]
    assert validate_records.check_schema(record, _validator())


def test_a_null_to_is_refused():
    assert validate_records.check_schema(_record(to=None), _validator())


def test_an_unknown_entry_member_is_refused():
    assert validate_records.check_schema(_record(note="x"), _validator())


def test_revisions_out_of_date_order_are_refused():
    record = _record()
    record["revisions"].insert(0, dict(record["revisions"][0], date="2026-09-29"))
    record["last_updated"] = "2026-09-29T00:00:00Z"
    errors = validate_records.check_revisions_append_only(record)
    assert any("date order" in error for error in errors)


def test_a_revision_after_last_updated_is_refused():
    record = _record()
    record["last_updated"] = "2026-08-07T00:00:00Z"
    errors = validate_records.check_revisions_append_only(record)
    assert any("predates the latest revision" in error for error in errors)


def test_a_record_without_revisions_makes_no_claim():
    record = copy.deepcopy(BASE)
    del record["revisions"]
    assert validate_records.check_revisions_append_only(record) == []
