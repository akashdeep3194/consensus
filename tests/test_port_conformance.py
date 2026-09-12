"""Port conformance suite.

Every adapter must satisfy the same behavioural contract, not merely the same
method names. This suite is written against the Protocols and parameterised by
adapter factory, so adding the Postgres adapter in M3 means adding one fixture
param — not a second copy of these assertions.

If a substitute cannot pass unchanged, it is not a valid substitute.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from adapters.memory import (
    InMemoryDraftRepository,
    InMemoryRoundRepository,
    InMemorySubmissionRepository,
)
from domain.lifecycle import RoundStatus
from domain.schedule import schedule_for
from ports.repositories import (
    CommittedEntry,
    ConcurrentModification,
    Draft,
    DraftRepository,
    DraftScanner,
    RoundClosed,
    RoundNotFound,
    RoundReader,
    RoundRecord,
    RoundWriter,
    SubmissionReader,
    SubmissionWriter,
)
from tests.conftest import run  # one shared event loop

ANCHOR = datetime(2026, 9, 12, tzinfo=UTC)




@pytest.fixture(params=["memory", "postgres"])
def repos(request):
    """Yields (rounds, drafts, submissions) for each adapter under test.

    Adding an adapter means adding a param here — never a second copy of the
    assertions below. An adapter that cannot pass unchanged is not a substitute.
    """
    if request.param == "memory":
        rounds = InMemoryRoundRepository()
        return rounds, InMemoryDraftRepository(rounds), InMemorySubmissionRepository(rounds)

    pool = request.getfixturevalue("pg_pool")
    from adapters.postgres import (
        PostgresDraftRepository,
        PostgresRoundRepository,
        PostgresSubmissionRepository,
    )

    run(pool.execute("TRUNCATE submissions, round_drafts, rounds, users CASCADE"))
    rounds = PostgresRoundRepository(pool)
    return rounds, PostgresDraftRepository(pool), PostgresSubmissionRepository(pool)


def new_user(repos) -> UUID:
    """A user id that exists in whichever store is under test.

    Postgres enforces a real foreign key to `users`; the in-memory adapter has
    no such table. The helper hides that difference so the assertions stay
    identical across adapters.
    """
    rounds = repos[0]
    user_id = uuid4()
    pool = getattr(rounds, "_pool", None)
    if pool is not None:
        run(
            pool.execute(
                """INSERT INTO users (user_id, external_id, provider)
                   VALUES ($1,$2,'test') ON CONFLICT DO NOTHING""",
                user_id, str(user_id),
            )
        )
    return user_id


def make_round(rounds, status=RoundStatus.OPEN, cycle=1):
    rec = RoundRecord(
        round_id=uuid4(),
        cycle_number=cycle,
        status=status,
        schedule=schedule_for(cycle, ANCHOR),
        ruleset_version="1.1",
        algorithm_version="1.1.0",
    )
    run(rounds.create(rec))
    return rec


# ── the adapters actually implement the protocols ───────────────────
def test_adapters_satisfy_their_protocols(repos):
    """Structural check only — runtime_checkable verifies method NAMES, not
    signatures or behaviour. The rest of this suite is what proves the contract."""
    rounds, drafts, submissions = repos
    assert isinstance(rounds, RoundReader) and isinstance(rounds, RoundWriter)
    assert isinstance(drafts, DraftRepository) and isinstance(drafts, DraftScanner)
    assert isinstance(submissions, SubmissionReader)
    assert isinstance(submissions, SubmissionWriter)


# ── rounds ──────────────────────────────────────────────────────────
def test_missing_round_raises_round_not_found(repos):
    rounds, _, _ = repos
    with pytest.raises(RoundNotFound):
        run(rounds.get(uuid4()))


def test_duplicate_cycle_number_is_rejected(repos):
    rounds, _, _ = repos
    make_round(rounds, cycle=7)
    with pytest.raises(ValueError):
        make_round(rounds, cycle=7)


def test_transition_is_compare_and_set(repos):
    rounds, _, _ = repos
    rec = make_round(rounds, status=RoundStatus.OPEN)
    moved = run(rounds.transition(rec.round_id, RoundStatus.OPEN, RoundStatus.BLACKOUT))
    assert moved.status is RoundStatus.BLACKOUT
    # the second worker, still believing the round is OPEN, must lose
    with pytest.raises(ConcurrentModification):
        run(rounds.transition(rec.round_id, RoundStatus.OPEN, RoundStatus.BLACKOUT))


def test_illegal_transition_is_refused_by_the_adapter_too(repos):
    from domain.lifecycle import IllegalTransition

    rounds, _, _ = repos
    rec = make_round(rounds, status=RoundStatus.OPEN)
    with pytest.raises(IllegalTransition):
        run(rounds.transition(rec.round_id, RoundStatus.OPEN, RoundStatus.REVEALED))


def test_live_excludes_revealed_and_voided(repos):
    rounds, _, _ = repos
    a = make_round(rounds, cycle=1)
    b = make_round(rounds, cycle=2)
    run(rounds.transition(b.round_id, RoundStatus.OPEN, RoundStatus.VOIDED))
    assert [r.round_id for r in run(rounds.live())] == [a.round_id]


# ── drafts ──────────────────────────────────────────────────────────
def test_draft_create_then_update_bumps_version(repos):
    rounds, drafts, _ = repos
    rec = make_round(rounds)
    user = new_user(repos)
    d1 = run(drafts.upsert(rec.round_id, user, "527", 5, None))
    assert d1.version == 1 and d1.is_complete
    d2 = run(drafts.upsert(rec.round_id, user, "123", 5, d1.version))
    assert d2.version == 2 and d2.prediction == "123"


def test_stale_version_is_rejected(repos):
    """Two tabs must not silently overwrite each other (§5.2)."""
    rounds, drafts, _ = repos
    rec = make_round(rounds)
    user = new_user(repos)
    d1 = run(drafts.upsert(rec.round_id, user, "527", 5, None))
    run(drafts.upsert(rec.round_id, user, "123", 1, d1.version))
    with pytest.raises(ConcurrentModification):
        run(drafts.upsert(rec.round_id, user, "456", 4, d1.version))   # stale


def test_updating_a_missing_draft_is_rejected(repos):
    rounds, drafts, _ = repos
    rec = make_round(rounds)
    with pytest.raises(ConcurrentModification):
        run(drafts.upsert(rec.round_id, new_user(repos), "527", 5, 1))


def test_partial_draft_is_not_complete(repos):
    rounds, drafts, _ = repos
    rec = make_round(rounds)
    d = run(drafts.upsert(rec.round_id, new_user(repos), "527", None, None))
    assert not d.is_complete


def test_scanner_returns_only_complete_drafts_in_chunks(repos):
    rounds, drafts, _ = repos
    rec = make_round(rounds)
    for _ in range(5):
        run(drafts.upsert(rec.round_id, new_user(repos), "527", 5, None))
    run(drafts.upsert(rec.round_id, new_user(repos), "527", None, None))   # incomplete
    assert run(drafts.count_complete(rec.round_id)) == 5

    async def collect():
        return [c async for c in drafts.iter_complete(rec.round_id, 2)]

    chunks = run(collect())
    assert [len(c) for c in chunks] == [2, 2, 1]
    assert all(d.is_complete for c in chunks for d in c)


def test_scan_order_is_deterministic(repos):
    """Seal-time ordering must be reproducible by an auditor (F4)."""
    rounds, drafts, _ = repos
    rec = make_round(rounds)
    for _ in range(8):
        run(drafts.upsert(rec.round_id, new_user(repos), "527", 5, None))

    async def ids():
        return [d.user_id async for c in drafts.iter_complete(rec.round_id, 3) for d in c]

    assert run(ids()) == run(ids())


def test_drafts_rejected_once_the_round_stops_accepting(repos):
    rounds, drafts, _ = repos
    rec = make_round(rounds, status=RoundStatus.OPEN)
    for frm, to in [
        (RoundStatus.OPEN, RoundStatus.BLACKOUT),
        (RoundStatus.BLACKOUT, RoundStatus.SEALING),
        (RoundStatus.SEALING, RoundStatus.SEALED),
    ]:
        run(rounds.transition(rec.round_id, frm, to))
    with pytest.raises(RoundClosed):
        run(drafts.upsert(rec.round_id, new_user(repos), "527", 5, None))


def test_drafts_still_accepted_during_blackout(repos):
    rounds, drafts, _ = repos
    rec = make_round(rounds, status=RoundStatus.OPEN)
    run(rounds.transition(rec.round_id, RoundStatus.OPEN, RoundStatus.BLACKOUT))
    assert run(drafts.upsert(rec.round_id, new_user(repos), "527", 5, None)).is_complete


# ── submissions ─────────────────────────────────────────────────────
def test_commit_allocates_sequential_numbers_from_one(repos):
    rounds, _, subs = repos
    rec = make_round(rounds)
    seqs = [
        run(subs.commit_entry(rec.round_id, new_user(repos), "527", 5, True, None)).commit_sequence
        for _ in range(4)
    ]
    assert seqs == [1, 2, 3, 4]


def test_one_entry_per_user_per_round(repos):
    rounds, _, subs = repos
    rec = make_round(rounds)
    user = new_user(repos)
    run(subs.commit_entry(rec.round_id, user, "527", 5, True, None))
    with pytest.raises(ConcurrentModification):
        run(subs.commit_entry(rec.round_id, user, "123", 1, True, None))


def test_idempotent_retry_returns_the_same_entry(repos):
    """A network failure after commit must not create a second row (§6.3)."""
    rounds, _, subs = repos
    rec = make_round(rounds)
    user = new_user(repos)
    a = run(subs.commit_entry(rec.round_id, user, "527", 5, True, "key-1"))
    b = run(subs.commit_entry(rec.round_id, user, "527", 5, True, "key-1"))
    assert a == b
    assert run(subs.count(rec.round_id)) == 1


def test_commit_rejected_once_the_round_closes(repos):
    rounds, _, subs = repos
    rec = make_round(rounds, status=RoundStatus.OPEN)
    for frm, to in [
        (RoundStatus.OPEN, RoundStatus.BLACKOUT),
        (RoundStatus.BLACKOUT, RoundStatus.SEALING),
        (RoundStatus.SEALING, RoundStatus.SEALED),
    ]:
        run(rounds.transition(rec.round_id, frm, to))
    with pytest.raises(RoundClosed):
        run(subs.commit_entry(rec.round_id, new_user(repos), "527", 5, True, None))


def test_iter_round_yields_commit_sequence_order(repos):
    rounds, _, subs = repos
    rec = make_round(rounds)
    for _ in range(5):
        run(subs.commit_entry(rec.round_id, new_user(repos), "527", 5, False, None))

    async def collect():
        return [e async for c in subs.iter_round(rec.round_id, 2) for e in c]

    assert [e.commit_sequence for e in run(collect())] == [1, 2, 3, 4, 5]


def test_entries_carry_everything_the_engine_needs(repos):
    """The port's data must map onto engine.Submission without a lookup."""
    rounds, _, subs = repos
    rec = make_round(rounds)
    e = run(subs.commit_entry(rec.round_id, new_user(repos), "527", 5, True, None))
    assert isinstance(e, CommittedEntry)
    assert {"prediction", "vote", "commit_sequence", "mandate_eligible"} <= set(
        CommittedEntry.__slots__
    )
    assert isinstance(Draft.is_complete, property)
