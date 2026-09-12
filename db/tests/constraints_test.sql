-- Every constraint must be shown to FIRE. A constraint nobody has seen reject
-- something is only a comment. Each block asserts a specific rejection.
\set ON_ERROR_STOP on
\set QUIET on
SET client_min_messages = notice;

CREATE OR REPLACE FUNCTION must_fail(sql text, label text) RETURNS void AS $$
BEGIN
  BEGIN
    EXECUTE sql;
  EXCEPTION WHEN others THEN
    RAISE NOTICE '  PASS  %  (%)', rpad(label, 46), left(SQLERRM, 58);
    RETURN;
  END;
  RAISE EXCEPTION 'FAIL  % — the statement was ACCEPTED but should have been rejected', label;
END;
$$ LANGUAGE plpgsql;

BEGIN;

INSERT INTO users (user_id, external_id, provider)
VALUES ('11111111-1111-1111-1111-111111111111', 'ext-1', 'google'),
       ('22222222-2222-2222-2222-222222222222', 'ext-2', 'google');

INSERT INTO rounds (round_id, cycle_number, status, opens_at, mandate_deadline,
                    blackout_at, seals_at, reveals_at, ruleset_version, algorithm_version)
VALUES ('aaaaaaaa-0000-0000-0000-000000000001', 999000001, 'open',
        '2026-09-12T00:00Z', '2026-09-12T12:00Z', '2026-09-12T23:00Z',
        '2026-09-13T00:00Z', '2026-09-13T06:00Z', '1.1', '1.1.0');

\echo 'domains — the shape of a valid value'
SELECT must_fail($$INSERT INTO round_drafts (round_id,user_id,prediction) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','112')$$,
  'prediction with repeated digits');
SELECT must_fail($$INSERT INTO round_drafts (round_id,user_id,prediction) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','12a')$$,
  'prediction with a non-digit');
SELECT must_fail($$INSERT INTO round_drafts (round_id,user_id,vote) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111',10)$$,
  'vote outside 0-9');

\echo 'rounds — phase ordering and state machine'
SELECT must_fail($$INSERT INTO rounds (round_id,cycle_number,opens_at,mandate_deadline,
  blackout_at,seals_at,reveals_at,ruleset_version,algorithm_version) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000009',999000009,'2026-09-12T00:00Z','2026-09-11T00:00Z',
   '2026-09-12T23:00Z','2026-09-13T00:00Z','2026-09-13T06:00Z','1.1','1.1.0')$$,
  'mandate deadline before open');
SELECT must_fail($$UPDATE rounds SET status='revealed'
  WHERE round_id='aaaaaaaa-0000-0000-0000-000000000001'$$,
  'illegal transition open -> revealed');
SELECT must_fail($$UPDATE rounds SET winning_number='527'
  WHERE round_id='aaaaaaaa-0000-0000-0000-000000000001'$$,
  'winning number before resolution');
SELECT must_fail($$UPDATE rounds SET commitment_root=repeat('a',64)
  WHERE round_id='aaaaaaaa-0000-0000-0000-000000000001'$$,
  'commitment root before seal');

\echo 'drafts'
INSERT INTO round_drafts (round_id, user_id, prediction, vote)
VALUES ('aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','527',5);
SELECT must_fail($$INSERT INTO round_drafts (round_id,user_id,prediction,vote) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','123',1)$$,
  'second draft for the same user');

\echo 'submissions'
INSERT INTO submissions (submission_id, round_id, user_id, prediction, vote,
                         commit_sequence, source, mandate_eligible)
VALUES ('bbbbbbbb-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000001',
        '11111111-1111-1111-1111-111111111111','527',5,1,'manual',true);

SELECT must_fail($$INSERT INTO submissions (submission_id,round_id,user_id,prediction,vote,
  commit_sequence,source,mandate_eligible) VALUES
  ('bbbbbbbb-0000-0000-0000-000000000002','aaaaaaaa-0000-0000-0000-000000000001',
   '11111111-1111-1111-1111-111111111111','123',1,2,'manual',false)$$,
  'second submission for the same user');
SELECT must_fail($$INSERT INTO submissions (submission_id,round_id,user_id,prediction,vote,
  commit_sequence,source,mandate_eligible) VALUES
  ('bbbbbbbb-0000-0000-0000-000000000003','aaaaaaaa-0000-0000-0000-000000000001',
   '22222222-2222-2222-2222-222222222222','123',1,1,'manual',false)$$,
  'duplicate commit_sequence in a round');
SELECT must_fail($$UPDATE submissions SET prediction='123'
  WHERE submission_id='bbbbbbbb-0000-0000-0000-000000000001'$$,
  'editing a committed submission');
SELECT must_fail($$UPDATE submissions SET vote=9
  WHERE submission_id='bbbbbbbb-0000-0000-0000-000000000001'$$,
  'editing a committed vote');
SELECT must_fail($$DELETE FROM submissions
  WHERE submission_id='bbbbbbbb-0000-0000-0000-000000000001'$$,
  'deleting a submission');

\echo 'voiding is the one permitted mutation'
UPDATE submissions SET voided_at=now(), void_reason='sybil cluster'
  WHERE submission_id='bbbbbbbb-0000-0000-0000-000000000001';
SELECT must_fail($$INSERT INTO submissions
  (submission_id,round_id,user_id,prediction,vote,commit_sequence,source,mandate_eligible,voided_at)
  VALUES ('bbbbbbbb-0000-0000-0000-00000000000f','aaaaaaaa-0000-0000-0000-000000000001',
  '22222222-2222-2222-2222-222222222222','345',3,7,'manual',false,now())$$,
  'voided_at without a void_reason');

\echo 'a closed round rejects writes through every path'
UPDATE rounds SET status='blackout' WHERE round_id='aaaaaaaa-0000-0000-0000-000000000001';
UPDATE rounds SET status='sealing'  WHERE round_id='aaaaaaaa-0000-0000-0000-000000000001';
UPDATE rounds SET status='sealed'   WHERE round_id='aaaaaaaa-0000-0000-0000-000000000001';
SELECT must_fail($$INSERT INTO round_drafts (round_id,user_id,prediction,vote) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001','22222222-2222-2222-2222-222222222222','345',3)$$,
  'draft written to a sealed round');
SELECT must_fail($$INSERT INTO submissions (submission_id,round_id,user_id,prediction,vote,
  commit_sequence,source,mandate_eligible) VALUES
  ('bbbbbbbb-0000-0000-0000-000000000004','aaaaaaaa-0000-0000-0000-000000000001',
   '22222222-2222-2222-2222-222222222222','345',3,4,'manual',false)$$,
  'submission written to a sealed round');
SELECT must_fail($$UPDATE rounds SET cycle_number=999000099
  WHERE round_id='aaaaaaaa-0000-0000-0000-000000000001'$$,
  'mutating a sealed round''s parameters');

ROLLBACK;
\echo ''
\echo 'ALL CONSTRAINT TESTS PASSED'
