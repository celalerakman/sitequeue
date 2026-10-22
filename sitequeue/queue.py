import hashlib
import json
import sqlite3
import uuid

SCHEMA = '''
CREATE TABLE IF NOT EXISTS jobs (
 id TEXT PRIMARY KEY, dedupe_key TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('ready','running','done','dead')),
 attempts INTEGER NOT NULL DEFAULT 0, available REAL NOT NULL,
 lease_until REAL, token TEXT, result TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS jobs_due ON jobs(state,available,lease_until);
'''


class Queue:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def submit(self, key, payload, now):
        if not isinstance(key, str) or not key.strip():
            raise ValueError('Non-empty idempotency key required')
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT * FROM jobs WHERE dedupe_key=?', (key,)).fetchone()
            if row:
                if row['payload'] != encoded:
                    raise ValueError('Idempotency key already belongs to a different payload')
                job_id = row['id']
            else:
                job_id = uuid.uuid4().hex
                self.db.execute('INSERT INTO jobs(id,dedupe_key,payload,state,available) VALUES (?,?,?,?,?)',
                                (job_id, key, encoded, 'ready', now))
            self.db.commit()
            return job_id
        except Exception:
            self.db.rollback()
            raise

    def claim(self, now, lease_seconds=30, max_attempts=3):
        if lease_seconds <= 0 or max_attempts < 1:
            raise ValueError('Positive lease and max_attempts required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute("UPDATE jobs SET state='dead',token=NULL,lease_until=NULL,error='Lease expired at attempt limit' WHERE state='running' AND lease_until<=? AND attempts>=?",
                            (now, max_attempts))
            row = self.db.execute("SELECT * FROM jobs WHERE attempts<? AND ((state='ready' AND available<=?) OR (state='running' AND lease_until<=?)) ORDER BY available,id LIMIT 1",
                                  (max_attempts, now, now)).fetchone()
            if row is None:
                self.db.commit()
                return None
            token = uuid.uuid4().hex
            self.db.execute("UPDATE jobs SET state='running', attempts=attempts+1,lease_until=?,token=? WHERE id=?",
                            (now + lease_seconds, token, row['id']))
            self.db.commit()
            return {**dict(row), 'token': token, 'attempts': row['attempts'] + 1,
                    'lease_until': now + lease_seconds, 'state': 'running',
                    'payload': json.loads(row['payload'])}
        except Exception:
            self.db.rollback()
            raise

    def complete(self, job_id, token, result, now):
        cursor = self.db.execute("UPDATE jobs SET state='done',result=?,token=NULL,lease_until=NULL WHERE id=? AND token=? AND state='running' AND lease_until>?",
                                 (json.dumps(result, allow_nan=False), job_id, token, now))
        return cursor.rowcount == 1

    def fail(self, job_id, token, error, now, max_attempts=3):
        cursor = self.db.execute("UPDATE jobs SET state=CASE WHEN attempts>=? THEN 'dead' ELSE 'ready' END,available=?+MIN(300, (1 << attempts)),error=?,token=NULL,lease_until=NULL WHERE id=? AND token=? AND state='running' AND lease_until>?",
                                 (max_attempts, now, str(error)[:500], job_id, token, now))
        return cursor.rowcount == 1

    def stats(self):
        counts = {state: 0 for state in ('ready','running','done','dead')}
        counts.update({row[0]: row[1] for row in self.db.execute('SELECT state,COUNT(*) FROM jobs GROUP BY state')})
        return counts

    def get(self, job_id):
        row = self.db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result.pop('token', None)
        result['payload'] = json.loads(result['payload'])
        result['result'] = json.loads(result['result']) if result['result'] else None
        return result

    def replay(self, job_id, now):
        """Explicit operator recovery; live jobs cannot be reset underneath a worker."""
        cursor = self.db.execute("UPDATE jobs SET state='ready',attempts=0,available=?,error=NULL,result=NULL WHERE id=? AND state='dead'",
                                 (now, job_id))
        return cursor.rowcount == 1


def artifact_result(payload):
    """Pure work: deterministic output can safely be recomputed after lease loss."""
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return {'sha256': hashlib.sha256(encoded.encode()).hexdigest(), 'bytes': len(encoded.encode())}
