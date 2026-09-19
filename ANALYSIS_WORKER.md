# Analysis worker

Apply the schema before starting the API and worker:

```sh
python manage.py migrate
python manage.py process_analyses
```

Run the worker as a supervised, persistent process alongside the API. It polls
pending matches (including newly ingested matches) and processes one at a time.
For a single queue drain use `python manage.py process_analyses --once`.
The browser polls the results endpoint while a job is pending or processing.
POSTing `{"eval_level":"2ply"}` to a match results endpoint queues a new run;
supported levels are 1ply, 2ply and 3ply. Luck retains its dedicated 2-ply evaluation.
The tournaments bridge checks session ownership before forwarding this request.

If a worker is forcibly stopped during a job, that match remains processing.
After confirming the old worker has stopped, reset that match to pending in the
database before restarting it. Do not reset a job with a live worker.

Player names are snapshots supplied by the game service with new match payloads.
Older immutable payloads without names retain the localized color fallback.
