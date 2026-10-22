import argparse
import json
import os
from pathlib import Path
import signal
import time
from .queue import Queue
from .work import execute

parser = argparse.ArgumentParser(description='Durable artifact-processing worker')
parser.add_argument('command', choices=['demo', 'worker', 'health', 'submit', 'show', 'replay'])
parser.add_argument('--db', default=os.environ.get('QUEUE_DB', 'runtime/queue.sqlite'))
parser.add_argument('--input', type=Path)
parser.add_argument('--key')
parser.add_argument('--id')
args = parser.parse_args()
Path(args.db).parent.mkdir(parents=True, exist_ok=True)
queue = Queue(args.db)
stopping = False


def stop(signum, frame):
    global stopping
    stopping = True


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
try:
    if args.command == 'health':
        if queue.db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise RuntimeError('Queue integrity check failed')
        print(json.dumps(queue.stats()))
    elif args.command == 'submit':
        if not args.input or not args.key:
            parser.error('--input and --key required')
        print(json.dumps({'id': queue.submit(args.key, json.loads(args.input.read_text(encoding='utf-8')), time.time())}))
    elif args.command in ('show', 'replay'):
        if not args.id:
            parser.error('--id required')
        if args.command == 'show':
            print(json.dumps(queue.get(args.id), indent=2))
        else:
            print(json.dumps({'replayed': queue.replay(args.id, time.time())}))
    else:
        if args.command == 'demo':
            queue.submit('synthetic-report-v1', {'project': 'SCHOOL-A', 'revision': 1}, time.time())
        while not stopping:
            job = queue.claim(time.time())
            if job:
                try:
                    result = execute(job['payload'])
                    accepted = queue.complete(job['id'], job['token'], result, time.time())
                    print(json.dumps({'event': 'completed' if accepted else 'lease_lost',
                                      'job': job['id']}), flush=True)
                except Exception as exc:
                    queue.fail(job['id'], job['token'], type(exc).__name__, time.time())
            elif args.command == 'demo':
                break
            else:
                time.sleep(0.5)
        print(json.dumps(queue.stats()), flush=True)
finally:
    queue.close()
