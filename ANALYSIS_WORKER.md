# Analysis worker

## Approved decision classification (09.10.2026)

The application now uses one shared classification policy in
`analysis/services/classification.py`. This is an approved application policy,
not a severity scale attributed to Open Sage:

| Saved equity loss | Label |
| --- | --- |
| `< 0.02` | `correct` |
| `>= 0.02` and `< 0.04` | `inaccuracy` |
| `>= 0.04` and `<= 0.08` | `error` |
| `> 0.08` | `blunder` (existing strict boundary retained) |

Only decisions scoreable under the existing checker/cube rules with a finite,
present saved `equity_loss` receive these labels. Missing/nonfinite loss, forced
or trivial decisions, unsupported types and incomplete scoreability data remain
`unclassified`; missing loss is never treated as zero. Checker/cube processors
classify before insertion using the model's six-decimal stored loss precision.

Game and match summaries count `error` and `blunder` as disjoint categories;
inaccuracies are not errors and blunders are not counted twice. PR, equity-loss
aggregation and the analyzed-decision denominator remain unchanged: only
scoreable decisions with non-null loss enter the existing scoring calculations.
Empty summaries have zero error/blunder counts.

Results GETs derive both decision labels and player error/blunder counts from
saved decision metrics (including legacy rows with stale labels/counts). Detail
reads use prefetched player/game/decision relationships. Lists return five
authorized summaries per request, projecting only summary payload fields and
streaming potentially counted decisions in batches of 25 with only their
scoring inputs. They do not rerun the engine,
update saved labels/counts, backfill the database or modify saved PR/luck/rating.
Lists do not materialize all game/decision relationships or full input/raw JSON.
The response includes count and next_offset; authorized filtering happens before
counting/slicing, with a stable creation-date/UUID order. Runtime verification
and coordinated deployment with the tournament bridge/client remain pending.
No schema migration is required. Other readers of persisted legacy summaries
still see their saved counts until ordinary reprocessing updates them.

Regression coverage was added for exact boundaries, missing/nonfinite metrics,
unscoreable decisions, both processors, game/match counts and read-only legacy
API classification. AST parsing and in-memory Python compilation passed for
all 11 changed/new Python files; no application modules were executed. Tests,
build and live match verification have **not** been run by the assistant. No
database operation, migration, engine run, commit or deployment was performed.
The user can run:

```sh
python manage.py test analysis.tests.test_classification analysis.tests.test_scoring analysis.tests.test_checker_processor analysis.tests.test_cube_processor analysis.tests.test_player_summary analysis.tests.test_player_match_summary analysis.tests.test_results_api
```

## Worker operation

> **עדכון תיעוד 19.09.2026 — נוהל מתוחזק.** העובד והתמיכה ב־1ply/2ply/3ply תואמים לקוד. שירות זה מספק גם bot/move עבור AI, עם match ו־action=move|cube; רמת הבוט היא 1ply בנפרד מעומק ניתוח המשחק. requirements.txt נועל Django 6.1.1 ואת commit חבילת bgsage; אין להסיק שהחבילות הותקנו או שהעובד פועל.
>
> [מצב המערכת העדכני](<../CURRENT_STATE.he.md>) · [מפתח התיעוד](<../docs/README.md>). עדכון זה מבוסס על קוד מקומי; בדיקות וספירות בגוף המסמך נשארות מתוארכות למועד ביצוען.

Install dependencies and the CPU-appropriate engine before applying the schema:

PostgreSQL is required locally and on the server. Configure `DB_NAME`, `DB_USER`
and `DB_PASSWORD` in this service's private `.env` or process environment;
`DB_HOST` defaults to `127.0.0.1` and `DB_PORT` to `5432` for native local use.
`.env.example` contains the non-secret template. Docker keeps the same explicit
`DB_*` profile and also requires `DB_HOST`. Both the API and `process_analyses`
must use the same database. `DATABASE_URL` is not a replacement for `DB_*` here;
SQLite and other non-PostgreSQL URLs are rejected rather than ignored.

The PostgreSQL driver is in base `requirements.txt`, so local and server installs
both receive it. No SQLite file is opened or created by these settings. Existing
legacy-data import, database provisioning and cutover require their own operation;
switching settings does not transfer or erase data. Run checks/tests against an
explicit disposable PostgreSQL database with a test login allowed to create it.

```sh
.venv/bin/python -m pip install -r requirements-server.txt
.venv/bin/python scripts/install_open_sage.py
.venv/bin/python manage.py migrate
```

`requirements.txt` now contains only the Python runtime dependencies; it deliberately
does not reinstall the upstream `bgsage` wheel. Fresh installations must run the
engine installer. Existing compatible installations survive ordinary dependency
updates. The installer is also the engine upgrade/rebuild entry point.

On Linux x86-64 it checks every processor's AVX2 and FMA flags. If either is absent
(or flags are unavailable), it builds the pinned upstream revision with baseline
`-march=x86-64 -mtune=generic` and disables the unconditional `BGBOT_USE_AVX2`
definition in `cpp/src/neural_net.cpp`, selecting upstream's scalar fallback.
Use `--compatible` to explicitly select this mode on the current Ivy Bridge VPS.
Both replacements are checked against the expected source before editing; model
weights and the engine revision are unchanged. Scalar performance and floating-point
rounding can differ from AVX2. The final check loads the engine and evaluates a move.

The saved wheels are in `.engine-build/compatible/` or `.engine-build/upstream/`,
ignored by Git. Build tools required on Ubuntu: `git`, `python3-venv`, `python3-dev`,
`build-essential`, and `cmake`. Builds default to two parallel jobs.
Do not reinstall `bgsage` directly from PyPI or the Git URL on this VPS: the
upstream x86 build forces AVX2/FMA and crashes here with exit code 132.

Upstream sources at the pinned revision:
- [CPU build flags](https://github.com/markbgsage/bgsage/blob/d8325a491168062df1047ffd998f3a5dfb426a0c/cpp/CMakeLists_cpu.txt)
- [AVX2/scalar implementation](https://github.com/markbgsage/bgsage/blob/d8325a491168062df1047ffd998f3a5dfb426a0c/cpp/src/neural_net.cpp)

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

AI practice matches use this same worker and the pinned Open Sage engine. Their
source type is `ai`; the opponent has `kind: "ai"`, `player_id: null`, and the
display name `Open Sage`. Human players still require an ID. Apply migration
`0005` before accepting AI payloads. The club authorizes results using the
player's saved practice-room purchase, including resumed legacy free rooms.

The game service must also run `python manage.py run_tasks` on its regular
schedule to retry its durable analysis delivery queue. Configure the same
`ANALYSIS_SERVICE_URL` and `ANALYSIS_API_TOKEN` in the game/club/analysis services
as applicable. In local development the game frontend proxies
`/tournaments-api/analyses` to the club backend; `VITE_TOURNAMENTS_URL` must point
to the running club frontend for Full analysis and Play again links.
