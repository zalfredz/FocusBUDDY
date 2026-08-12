# ML Outcome Data Collection

## What FocusBuddy collects and why

Phase 3 collects only the minimum task, prediction, Focus timing, outcome, and
provenance fields defined in `ML_USER_OUTCOME_DATA_SCHEMA.md`. It does not add
Google account details, contact data, Diary text, mood text, medication data, or
payment data to the ML outcome row.

Task text is necessary for the Duration feature representation. Task ID,
session ID, occurrence date, and internal user UUID exist to reconstruct the
label and prevent evaluation leakage. Prediction version distinguishes outcomes
made under different model behavior. Pause/interruption fields prevent wall time
from masquerading as active work.

## Runtime collection is not runtime training

The runtime path performs UUID creation, arithmetic, JSON persistence, and the
existing Supabase state sync. It does not import `ml.training`, call `fit`, choose
hyperparameters, replace an artifact, or call an external AI duration API.

```text
user outcome -> stored only

NOT:
user outcome -> model.fit() -> replacement model
```

The known legacy runtime-training locations remain documented in
`RUNTIME_TRAINING_LOCATIONS.md`. Phase 3 does not add to, invoke, or remove those
locations because production inference replacement is outside this phase.

## Offline validation and building

The implementation is split into:

- `ml.evaluation.user_outcomes.validate_outcome_records()`: duplicate, identity,
  association, prediction, timestamp, duration, demo/test, and reliability checks;
- `ml.datasets.user_outcomes.join_supabase_state_rows()`: joins the authenticated
  user envelope with task/session snapshots;
- `ml.datasets.user_outcomes.build_training_dataset()`: aggregates valid session
  histories into complete task-occurrence candidates;
- `ml.datasets.user_outcomes.write_training_dataset()`: writes an explicit
  versioned CSV/JSON snapshot.

An approved offline operator supplies exported Supabase rows shaped as:

```json
[{"user_id": "internal-uuid", "state": {"tasks": [], "ml_outcome_records": []}}]
```

The `state` value may also be a serialized JSON string. No runtime process calls
the builder. Output reports should consume only its `audit` counts; raw IDs and
task text stay inside the restricted dataset snapshot.

## Data-quality handling

The validator never deletes records. It attaches a status and reason:

- `valid`: internally consistent, positive, pause-aware measurement;
- `suspicious`: structurally usable but requires review, currently >8 hours;
- `invalid`: corrupt, duplicate, impossible, test/legacy-ambiguous demo, or
  missing provenance;
- `unknown`: unfinished or timing cannot be reconstructed.

Unknown is never converted to zero. Suspicious rows are retained for audit but
excluded from the default training builder. A task candidate is rejected if any
session needed for its total has incomplete/invalid history.

## Synthetic fixture

`ml/datasets/fixtures/user_outcomes_v1.synthetic.json` contains two explicitly
synthetic sessions. It tests joins, aggregation, validation, and writers only.
Even when the test-only builder switch permits it through the pipeline, the
result remains `synthetic=true` and `training_eligible=false`. It cannot support
an accuracy claim.

## Leakage-safe future evaluation

Source `user_id`, `task_id`, `occurrence_date`, `task_family_id`, and session IDs
are retained for splitting, not prediction. With enough users, the preferred
locked test is group-aware by user so one user's nearly identical behavior cannot
appear on both sides. If user count is too small, use an earlier-history/later-
history temporal split per user and keep every task family on one side only.

Preprocessing and model selection remain fit on training data only. The locked
test remains untouched until selection is frozen, consistent with Phases 0–2.

## Provisional cold start

- 0 outcomes: global production behavior.
- 1–4 outcomes: global behavior.
- 5–29 outcomes: collect and evaluate offline; no personalization.
- 30+ valid completed outcomes: candidate for a future personalization
  experiment, not automatic personalization.

The 30-outcome gate also requires 14 active days and 3 categories. These are
Phase 4 planning assumptions, not validated scientific cutoffs.

## Data still needed

- enough real completed task occurrences across multiple users;
- repeated categories and task sizes, especially long tasks;
- visibility/background telemetry if product and privacy review approve it;
- explicit task edits or deletion provenance if later flows allow them;
- evidence to set reasonable duration limits by task type;
- sufficient users to reserve a user-grouped locked test.

No Phase 4 training should begin until collection volume, completion coverage,
quality-status distribution, and privacy handling are reviewed.
