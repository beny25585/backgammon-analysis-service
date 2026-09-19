# Analysis worker

> **עדכון תיעוד 19.09.2026 — נוהל מתוחזק.** העובד והתמיכה ב־1ply/2ply/3ply תואמים לקוד. שירות זה מספק גם bot/move עבור AI, עם match ו־action=move|cube; רמת הבוט היא 1ply בנפרד מעומק ניתוח המשחק. requirements.txt נועל Django 6.1.1 ואת commit חבילת bgsage; אין להסיק שהחבילות הותקנו או שהעובד פועל.
>
> [מצב המערכת העדכני](<../CURRENT_STATE.he.md>) · [מפתח התיעוד](<../docs/README.md>). עדכון זה מבוסס על קוד מקומי; בדיקות וספירות בגוף המסמך נשארות מתוארכות למועד ביצוען.

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
