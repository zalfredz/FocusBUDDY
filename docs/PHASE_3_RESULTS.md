# Phase 3 — Real User Outcome Data Collection Results

## Outcome

Phase 3 establishes a versioned, pause-aware real-outcome collection path and an
offline validator/dataset builder. It does not train, deploy, replace, or convert
any model. No accuracy result is claimed.

The key modeling decision is that a supervised Duration row represents one
completed **task occurrence**, not one Pomodoro. Multiple reliable Focus sessions
are summed only after the corresponding task occurrence is complete.

## Answers required by Phase 3

1. **Where does FocusBuddy currently obtain task duration?** Tracker calls
   `models.model_durasi.perkirakan()`. The chosen estimate is stored as
   `task.menit_est`; new Tracker-created predictions also store a versioned
   `task.duration_prediction` snapshot. Existing runtime prediction behavior is
   unchanged.
2. **Where can actual active duration be measured?** `app.focus_session` already
   derives consumed countdown time as total session seconds minus remaining
   seconds. Explicit pause freezes remaining time. Phase 3 persists this as
   `actual_active_duration_minutes` and separately records pause duration.
3. **Which existing events can be reused?** Task creation, Focus start,
   pause/resume, optional duration change, explicit Focus outcomes, task-step
   completion, `storage.save_state()`, and the Supabase cloud-save hook.
4. **Which fields were already available?** Task/step/occurrence identity, task
   title/category/importance/deadline, estimate, created time, Focus start/end,
   outcome, active focus minutes, and task completion state.
5. **Which fields were missing?** A stable Focus session ID, an unfinished session
   record, prediction model version/source/inputs, explicit interruption and pause
   totals, schema version, demo/synthetic provenance, and offline quality status.
6. **What minimum code changes were required?** Snapshot prediction metadata on
   Tracker task creation; materialize one versioned outcome record at Focus start;
   update that same record on pause/resume/duration change/end; reuse existing
   state/Supabase persistence; add a separate offline validator and builder.
7. **What becomes a valid supervised-learning example?** A non-demo,
   non-synthetic completed task occurrence with consistent prediction provenance
   and a complete history of positive, reliable, non-duplicate session
   measurements. Its target is the sum of session active minutes—not elapsed wall
   time and not the original estimate.
8. **How is data exported?** Export `user_id` plus `state` from authenticated
   Supabase rows, pass the rows to `build_training_dataset()`, review its aggregate
   audit, then explicitly write a versioned snapshot. Raw identifiers/text are not
   printed in aggregate reports.
9. **What prevents runtime retraining?** Production collection imports no offline
   training package and calls no fitting operation. The offline builder only
   validates/joins/writes rows. The Phase 0 offline training guard and experimental
   registry remain separate. Pre-existing legacy runtime-fit locations are still
   listed in `RUNTIME_TRAINING_LOCATIONS.md` and were not expanded in Phase 3.
10. **What is next after Phase 3?** Review collection/privacy semantics, deploy
    only the logging change if approved, collect enough real valid outcomes, audit
    quality and coverage, then specify Phase 4. Do not train from the synthetic
    fixture or from an insufficient user sample.

## Implementation inventory

- Runtime fields and persistence: `app/storage.py`.
- Pause-aware lifecycle: `app/focus_session.py`.
- Prediction provenance at task creation: `app/views/tracker.py` and the stable
  production-version identifier in `models/model_durasi.py`.
- Offline validator: `ml/evaluation/user_outcomes.py`.
- Offline join/aggregation/writer: `ml/datasets/user_outcomes.py`.
- Synthetic-only fixture: `ml/datasets/fixtures/user_outcomes_v1.synthetic.json`.
- Acceptance contracts: `tests/test_ml_phase3.py`.

## Safety and known limitations

- No production inference result, task ranking, Focus duration rule, UI flow,
  Supabase table, external AI call, TensorFlow, or TFLite behavior was changed.
- The collection uses the existing per-user Supabase state and Auth UUID; it adds
  no PII fields.
- Explicit pause time is excluded. Browser background/foreground visibility is
  not observed, so `timing_quality` declares that limitation.
- Legacy tasks without prediction version remain stored but are invalid for
  future training; Phase 3 does not invent their provenance.
- Runtime outcome storage is capped at 2,000 session records per user to bound the
  existing JSON-state payload. An export/retention policy should be reviewed
  before any user approaches that limit.
- Existing legacy runtime-fit locations were not removed because replacing
  production inference is explicitly outside this phase. Phase 3 introduces no
  new fit or retraining path.

## Stop condition

Phase 3 stops at collection, validation, aggregation, tests, and documentation.
No model was trained, deployed, promoted, or converted.
