"""Tests for budget_enforcer's pause path (in-place re-queue, 2026-09-23).

Run: python3 budget_enforcer_test.py   (plain python3; no google3 deps)

Everything that touches CNS or XM is faked: `ls_fn` stands in for `fileutil
ls`, `cancel_job` is patched, and the queue / ledger live in a temp dir.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import budget_enforcer as be  # noqa: E402

R = be._route_lib()

RUN = '/cns/xx-d/home/u/logs/elt-dit/xid_111_20260923_elt_foo-r2'
OLD_RUN = '/cns/xx-d/home/u/logs/elt-dit/xid_100_20260922_elt_foo-r1'


def fake_ls(tree):
  """ls_fn over a dict {dir: [child names]}; missing key -> 'absent';
  value None -> 'unknown' (CNS unreachable)."""
  def ls(path):
    path = path.rstrip('/')
    if path in tree:
      kids = tree[path]
      if kids is None:
        return 'unknown', ['fileutil rc=1 (CNS unreachable?)']
      return 'ok', [f'{path}/{k}' for k in kids]
    # a leaf listed inside its parent exists
    parent, name = path.rsplit('/', 1)
    if parent in tree and tree[parent] is None:
      return 'unknown', ['fileutil rc=1 (CNS unreachable?)']
    if name in (tree.get(parent) or []):
      return 'ok', [path]
    return 'absent', []
  return ls


def make_row(job_id='20260922T000000-aaaaaaaaaa', xid='111', auto_resumes=2,
             state='SUBMITTED', lk=None):
  e = R.QueueEntry(job_id=job_id, power='v7-32', allowed_archs=['v7', 'v6p'])
  e.name = 'elt_foo'
  e.state = R.JobState(state)
  e.launch_kwargs = dict(lk if lk is not None else {
      'config': 'loop_foo', 'exp_name': 'elt_foo-r2',
      'restart_from': OLD_RUN, 'restart_step': '100000'})
  e.auto_resumes = auto_resumes
  e.prior_xids = ['100']
  e.xid = xid
  e.cell = 'yucbful'
  e.arch = 'v7'
  e.chips = 32
  e.submitted_at = 1.0
  return e


class CheckpointGateTest(unittest.TestCase):

  def test_elt_newest_bare_int_leaf_wins_and_tmp_is_skipped(self):
    ls = fake_ls({f'{RUN}/checkpoints': [
        '120000', '130000', '140000.orbax-checkpoint-tmp-abc']})
    ok, ck = be._latest_complete_checkpoint(RUN, R, ls)
    self.assertIs(ok, True)
    self.assertEqual(ck, f'{RUN}/checkpoints/130000')

  def test_torch_step_file(self):
    ls = fake_ls({f'{RUN}/steps': ['step_500.pt', 'step_900.pt', '.step_1000.pt.tmp']})
    ok, ck = be._latest_complete_checkpoint(RUN, R, ls)
    self.assertIs(ok, True)
    self.assertEqual(ck, f'{RUN}/steps/step_900.pt')

  def test_run_dir_with_empty_checkpoints_is_not_a_checkpoint(self):
    # the r114 case: run dir exists, checkpoints/ is empty -> the OLD gate passed it
    ls = fake_ls({RUN: ['config.json', 'checkpoints'], f'{RUN}/checkpoints': []})
    ok, detail = be._latest_complete_checkpoint(RUN, R, ls)
    self.assertIs(ok, False)
    self.assertIn('no complete checkpoint', detail)

  def test_unreachable_cns_is_unknown_not_absent(self):
    ls = fake_ls({f'{RUN}/checkpoints': None})
    ok, _ = be._latest_complete_checkpoint(RUN, R, ls)
    self.assertIsNone(ok)

  def test_fresh_resume_falls_back_to_rows_verified_pointer(self):
    row = make_row()
    ls = fake_ls({f'{RUN}/checkpoints': [],
                  f'{OLD_RUN}/checkpoints': ['100000']})
    ok, ck = be._resume_checkpoint({'xid': '111', 'bucket_cp_path': RUN}, row, R,
                                   ls_fn=ls)
    self.assertIs(ok, True)
    self.assertEqual(ck, f'{OLD_RUN}/checkpoints/100000')

  def test_fallback_pointer_gone_is_refused(self):
    row = make_row()
    ls = fake_ls({f'{RUN}/checkpoints': []})
    ok, detail = be._resume_checkpoint({'xid': '111', 'bucket_cp_path': RUN}, row, R,
                                       ls_fn=ls)
    self.assertIs(ok, False)
    self.assertIn('is gone', detail)

  def test_cold_row_without_any_checkpoint_is_refused(self):
    row = make_row(lk={'config': 'c', 'exp_name': 'e'})
    ls = fake_ls({f'{RUN}/checkpoints': []})
    ok, _ = be._resume_checkpoint({'xid': '111', 'bucket_cp_path': RUN}, row, R,
                                  ls_fn=ls)
    self.assertIs(ok, False)


class QueueFixture(unittest.TestCase):

  def setUp(self):
    self.tmp = tempfile.mkdtemp()
    self.q = os.path.join(self.tmp, 'queue.json')
    self.jobs = os.path.join(self.tmp, 'jobs.json')
    self.legacy = os.path.join(self.tmp, 'jobs_legacy.json')
    with open(self.jobs, 'w') as f:
      json.dump({'111': {'status': 'SUBMITTED', 'exp_name': 'elt_foo-r2'},
                 '999': {'status': 'RUNNING'}}, f)
    self._patches = [
        mock.patch.dict(be._LEDGER_TO_QUEUE, {os.path.abspath(self.jobs): self.q}),
        mock.patch.dict(be._LEDGER_TO_LEGACY, {os.path.abspath(self.jobs): self.legacy}),
    ]
    for p in self._patches:
      p.start()

  def tearDown(self):
    for p in self._patches:
      p.stop()

  def write_queue(self, rows, schema=None):
    with open(self.q, 'w') as f:
      json.dump({'schema_version': schema or R.QUEUE_SCHEMA_VERSION,
                 'entries': [r.to_dict() for r in rows]}, f)

  def read_rows(self):
    with open(self.q) as f:
      return [R.QueueEntry.from_dict(d) for d in json.load(f)['entries']]


class RequeueInPlaceTest(QueueFixture):

  def test_row_goes_back_to_queued_warm_same_identity(self):
    self.write_queue([make_row()])
    ck = f'{RUN}/checkpoints/130000'
    ok, detail = be.requeue_in_place(self.q, '20260922T000000-aaaaaaaaaa', '111',
                                     ck, 'why', R)
    self.assertTrue(ok, detail)
    [e] = self.read_rows()
    self.assertEqual(e.job_id, '20260922T000000-aaaaaaaaaa')
    self.assertEqual(e.state, R.JobState.QUEUED)
    self.assertIsNone(e.xid)                      # holds no live xid now
    self.assertEqual(e.all_xids, ['100', '111'])  # history kept
    self.assertEqual(e.submissions[-1].ended_reason, 'budget pause (budget_enforcer)')
    self.assertEqual(e.launch_kwargs['config'], 'loop_foo')
    self.assertEqual(e.launch_kwargs['restart_from'], RUN)
    self.assertEqual(e.launch_kwargs['restart_step'], '130000')
    self.assertNotIn('load_from', e.launch_kwargs)
    self.assertEqual(e.launch_kwargs['exp_name'], 'elt_foo-r3')
    self.assertEqual(e.auto_resumes, 2)           # a pause is not a crash
    self.assertIsNone(e.cell)
    self.assertIsNone(e.submitted_at)

  def test_torch_pointer_uses_load_from(self):
    self.write_queue([make_row(lk={'config': 'c', 'exp_name': 'e'})])
    ck = f'{RUN}/steps/step_900.pt'
    ok, _ = be.requeue_in_place(self.q, '20260922T000000-aaaaaaaaaa', '111', ck, 'w', R)
    self.assertTrue(ok)
    [e] = self.read_rows()
    self.assertEqual(e.launch_kwargs['load_from'], ck)
    self.assertNotIn('restart_from', e.launch_kwargs)

  def test_row_no_longer_holding_xid_is_left_alone(self):
    self.write_queue([make_row(xid='222')])
    before = open(self.q).read()
    ok, detail = be.requeue_in_place(self.q, '20260922T000000-aaaaaaaaaa', '111',
                                     'x/checkpoints/1', 'w', R)
    self.assertFalse(ok)
    self.assertIn('now holds xid 222', detail)
    self.assertEqual(open(self.q).read(), before)

  def test_already_resumed_by_successor_is_left_alone(self):
    a = make_row()
    b = make_row(job_id='20260923T000000-bbbbbbbbbb', xid='333', state='QUEUED')
    b.prior_xids = ['111']
    b.xid = None
    self.write_queue([a, b])
    before = open(self.q).read()
    ok, detail = be.requeue_in_place(self.q, a.job_id, '111', 'x/checkpoints/1', 'w', R)
    self.assertFalse(ok)
    self.assertIn('already resumed', detail)
    self.assertEqual(open(self.q).read(), before)

  def test_schema_mismatch_is_refused(self):
    self.write_queue([make_row()], schema=99)
    ok, detail = be.requeue_in_place(self.q, '20260922T000000-aaaaaaaaaa', '111',
                                     'x/checkpoints/1', 'w', R)
    self.assertFalse(ok)
    self.assertIn('schema', detail)

  def test_find_queue_row_ambiguous(self):
    self.write_queue([make_row(), make_row(job_id='20260923T000000-cccccccccc')])
    e, why = be.find_queue_row(self.q, '111', R)
    self.assertIsNone(e)
    self.assertIn('ambiguous', why)


class PauseAndRequeueTest(QueueFixture):

  def r(self):
    return {'xid': '111', 'cost': 300.0, 'tpu_type': 'v7-32', 'tier': 'PROD',
            'name': 'elt_foo-r2', 'bucket_cp_path': RUN, 'has_stagedir': True}

  def run_pause(self, tree, dry_run=False, cancel_ok=True):
    ls = fake_ls(tree)
    calls = []
    def fake_cancel(xid, jobs_file, dry_run):
      calls.append(xid)
      return cancel_ok, 'cancelled' if cancel_ok else 'boom'
    with mock.patch.object(be, '_fileutil_ls', ls), \
         mock.patch.object(be, 'cancel_job', fake_cancel), \
         mock.patch.object(be, '_record_pending_resume',
                           lambda r, jf: (True, 'PENDING_FILE')):
      ok, out = be.pause_and_requeue(self.r(), self.jobs, dry_run=dry_run,
                                     local_queue_file=self.q)
    return ok, out, calls

  def test_armed_pause_requeues_row_and_archives_board(self):
    self.write_queue([make_row()])
    ok, out, calls = self.run_pause({f'{RUN}/checkpoints': ['130000']})
    self.assertTrue(ok, out)
    self.assertEqual(calls, ['111'])
    self.assertIn('re-queued IN PLACE', out)
    [e] = self.read_rows()
    self.assertEqual(e.state, R.JobState.QUEUED)
    self.assertEqual(e.launch_kwargs['restart_step'], '130000')
    self.assertEqual(e.auto_resumes, 2)
    board = json.load(open(self.jobs))
    self.assertNotIn('111', board)      # no CANCELLED ghost on `tpu check`
    self.assertIn('999', board)         # other rows untouched
    self.assertEqual(json.load(open(self.legacy))['111']['archived_by'],
                     'budget_enforcer (paused, re-queued in place)')

  def test_dry_run_mutates_nothing(self):
    self.write_queue([make_row()])
    before_q, before_j = open(self.q).read(), open(self.jobs).read()
    ok, out, calls = self.run_pause({f'{RUN}/checkpoints': ['130000']}, dry_run=True)
    self.assertTrue(ok)
    self.assertIn('[dry-run]', out)
    self.assertEqual(calls, [])
    self.assertEqual(open(self.q).read(), before_q)
    self.assertEqual(open(self.jobs).read(), before_j)

  def test_no_checkpoint_is_paused_and_requeued_cold(self):
    # operator 2026-09-23: a missing checkpoint no longer blocks the pause; the
    # row goes back to QUEUED with every resume pointer stripped (step 0).
    self.write_queue([make_row(lk={'config': 'c', 'exp_name': 'e-r1',
                                   'restart_from': OLD_RUN, 'restart_step': '5'})])
    tree = {f'{RUN}/checkpoints': []}          # current run: nothing; old pointer: gone
    before = open(self.q).read()
    ok, out, calls = self.run_pause(tree, dry_run=True)
    self.assertTrue(ok)
    self.assertIn('COLD', out)
    self.assertEqual(calls, [])
    self.assertEqual(open(self.q).read(), before)
    ok, out, calls = self.run_pause(tree)
    self.assertTrue(ok, out)
    self.assertEqual(calls, ['111'])
    self.assertIn('COLD', out)
    [e] = self.read_rows()
    self.assertEqual(e.state, R.JobState.QUEUED)
    for k in ('load_from', 'restart_from', 'restart_step'):
      self.assertNotIn(k, e.launch_kwargs)
    self.assertEqual(e.launch_kwargs['config'], 'c')
    self.assertEqual(e.launch_kwargs['exp_name'], 'e-r2')
    self.assertEqual(e.auto_resumes, 2)

  def test_cns_unreachable_keeps_rows_existing_pointer(self):
    # 'unknown' is never read as "no checkpoint": keep the pointer the row
    # already resumes from rather than silently throwing progress away.
    self.write_queue([make_row()])
    ok, out, calls = self.run_pause({f'{RUN}/checkpoints': None, OLD_RUN + '/checkpoints': None})
    self.assertTrue(ok, out)
    [e] = self.read_rows()
    self.assertEqual(e.launch_kwargs['restart_from'], OLD_RUN)
    self.assertEqual(e.launch_kwargs['restart_step'], '100000')
    self.assertIn('unverifiable', out)

  def test_requeue_row_in_place_cold_strips_pointers(self):
    e = be.requeue_row_in_place(R, make_row(), '111', None, 'w')
    self.assertEqual(e.state, R.JobState.QUEUED)
    self.assertNotIn('restart_from', e.launch_kwargs)
    self.assertNotIn('restart_step', e.launch_kwargs)

  def test_cancel_failure_leaves_row_alone(self):
    self.write_queue([make_row()])
    before = open(self.q).read()
    ok, out, _ = self.run_pause({f'{RUN}/checkpoints': ['130000']}, cancel_ok=False)
    self.assertFalse(ok)
    self.assertEqual(open(self.q).read(), before)

  def test_no_queue_row_keeps_old_withheld_path(self):
    self.write_queue([make_row(xid='222')])
    ok, out, calls = self.run_pause({f'{RUN}/checkpoints': ['130000']})
    self.assertTrue(ok)
    self.assertEqual(calls, ['111'])
    self.assertIn('WITHHELD', out)

  def test_mismatched_queue_file_refused(self):
    self.write_queue([make_row()])
    with mock.patch.object(be, 'cancel_job') as c:
      ok, out = be.pause_and_requeue(self.r(), self.jobs, dry_run=False,
                                     local_queue_file=os.path.join(self.tmp, 'other.json'))
    self.assertFalse(ok)
    c.assert_not_called()


if __name__ == '__main__':
  unittest.main()
