"""Schema contract — the database must agree with the domain.

The state machine is defined twice: canonically in `domain/lifecycle.py`, and
mirrored into `round_transitions` so PostgreSQL can enforce it (§6.1). Two
definitions of one rule is a drift risk, so it is tested rather than trusted.

This parses the migration directly, so it runs everywhere with no database.
`db/tests/constraints_test.sql` covers the live-database behaviour.
"""

import pathlib
import re

import pytest

from domain.lifecycle import ACCEPTING_ENTRIES, TRANSITIONS, RoundStatus

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "db" / "migrations"
INIT_SQL = (MIGRATIONS / "0001_init.sql").read_text()
ENTRIES_SQL = (MIGRATIONS / "0002_entries.sql").read_text()


def sql_transitions() -> set[tuple[str, str]]:
    block = re.search(
        r"INSERT INTO round_transitions.*?VALUES(.*?);", INIT_SQL, re.S
    )
    assert block, "round_transitions seed not found in 0001_init.sql"
    body = re.sub(r"--[^\n]*", "", block.group(1))
    return {
        (m.group(1), m.group(2))
        for m in re.finditer(r"\(\s*'([a-z]+)'\s*,\s*'([a-z]+)'\s*\)", body)
    }


def sql_enum_values() -> list[str]:
    block = re.search(r"CREATE TYPE round_status AS ENUM\s*\((.*?)\);", INIT_SQL, re.S)
    assert block
    return re.findall(r"'([a-z]+)'", block.group(1))


def test_status_enum_matches_the_domain():
    assert set(sql_enum_values()) == {s.value for s in RoundStatus}


def test_transition_table_matches_the_domain_exactly():
    """If this fails, the database and the application disagree on what is legal."""
    expected = {(f.value, t.value) for f, t in TRANSITIONS}
    assert sql_transitions() == expected


def test_no_transition_is_seeded_twice():
    body = re.search(r"INSERT INTO round_transitions.*?VALUES(.*?);", INIT_SQL, re.S).group(1)
    pairs = re.findall(r"\(\s*'([a-z]+)'\s*,\s*'([a-z]+)'\s*\)", re.sub(r"--[^\n]*", "", body))
    assert len(pairs) == len(set(pairs))


@pytest.mark.parametrize(
    "constraint",
    [
        "one_entry_per_user",          # engine InvalidSubmissionSet: duplicate user
        "commit_sequence_unique",      # engine InvalidSubmissionSet: duplicate sequence
        "commit_sequence_positive",
        "void_reason_with_void",
    ],
)
def test_submission_invariants_are_database_constraints(constraint):
    """Each engine-level structural invariant is also enforced by the schema."""
    assert constraint in ENTRIES_SQL


@pytest.mark.parametrize(
    "guard",
    [
        "submissions_are_immutable",       # §1.3 committed entries never change
        "submissions_no_delete",           # append-only
        "reject_write_to_closed_round",    # §6.2 post-seal writes rejected
        "enforce_round_transition",        # §6.1 DB is authoritative
        "freeze_sealed_round",
    ],
)
def test_protective_triggers_exist(guard):
    assert guard in INIT_SQL or guard in ENTRIES_SQL


def test_accepting_phases_agree_with_the_sql_guard():
    """The trigger's allow-list must match ACCEPTING_ENTRIES."""
    block = re.search(
        r"current_status NOT IN \(([^)]*)\)", ENTRIES_SQL
    )
    assert block
    allowed = set(re.findall(r"'([a-z]+)'", block.group(1)))
    assert allowed == {s.value for s in ACCEPTING_ENTRIES}


def test_prediction_domain_enforces_distinct_digits():
    """Ruleset V1.1 §1 — 720 valid slates, enforced in the type itself."""
    domain = re.search(r"CREATE DOMAIN prediction_slate.*?;", INIT_SQL, re.S).group(0)
    assert "digits_distinct" in domain
    assert "^[0-9]{3}$" in domain


def test_drafts_define_completeness_as_a_generated_column():
    """F6 — one definition, so the seal query and the API cannot drift."""
    assert "is_complete" in ENTRIES_SQL
    assert "GENERATED ALWAYS AS" in ENTRIES_SQL
