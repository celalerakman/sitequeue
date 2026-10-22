from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from pathlib import Path
from sitequeue.queue import Queue, artifact_result


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'queue.sqlite')
        self.q = Queue(self.path)

    def tearDown(self):
        self.q.close()
        self.temp.cleanup()

    def test_idempotency_and_payload_conflict(self):
        first = self.q.submit('a', {'value': 1}, 0)
        self.assertEqual(first, self.q.submit('a', {'value': 1}, 0))
        with self.assertRaises(ValueError):
            self.q.submit('a', {'value': 2}, 0)

    def test_expired_worker_cannot_complete_reclaimed_job(self):
        self.q.submit('a', {}, 0)
        old = self.q.claim(0, 5)
        current = self.q.claim(6, 5)
        self.assertFalse(self.q.complete(old['id'], old['token'], {}, 7))
        self.assertTrue(self.q.complete(current['id'], current['token'], {}, 7))
        self.assertEqual(self.q.stats()['done'], 1)

    def test_expired_lease_cannot_complete_without_reclaim(self):
        self.q.submit('a', {}, 0)
        job = self.q.claim(0, 5)
        self.assertFalse(self.q.complete(job['id'], job['token'], {}, 5))

    def test_retry_backoff_then_dead_letter(self):
        self.q.submit('a', {}, 0)
        for now in (0, 3, 8):
            job = self.q.claim(now)
            self.assertIsNotNone(job)
            self.assertTrue(self.q.fail(job['id'], job['token'], 'temporary', now))
            self.assertIsNone(self.q.claim(now + 1))
        self.assertEqual(self.q.stats()['dead'], 1)

    def test_crashing_workers_reach_attempt_limit(self):
        self.q.submit('a', {}, 0)
        for now in (0, 2, 4):
            self.assertIsNotNone(self.q.claim(now, 1))
        self.assertIsNone(self.q.claim(6, 1))
        self.assertEqual(self.q.stats()['dead'], 1)

    def test_two_workers_never_claim_same_live_job(self):
        for index in range(20):
            self.q.submit(str(index), {'index':index}, 0)

        def claim_all(_):
            worker = Queue(self.path)
            claimed = []
            try:
                while job := worker.claim(0):
                    claimed.append(job['id'])
            finally:
                worker.close()
            return claimed

        with ThreadPoolExecutor(max_workers=2) as pool:
            batches = list(pool.map(claim_all, range(2)))
        all_ids = batches[0] + batches[1]
        self.assertEqual(len(all_ids), 20)
        self.assertEqual(len(set(all_ids)), 20)

    def test_deterministic_artifact_result(self):
        self.assertEqual(artifact_result({'a':1,'b':2}), artifact_result({'b':2,'a':1}))


if __name__ == '__main__':
    unittest.main()
