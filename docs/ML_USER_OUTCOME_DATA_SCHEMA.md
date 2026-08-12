# ML User Outcome Data Schema

## Unit of observation

FocusBuddy stores one `focus-outcome-v1` record for every Focus session. The
future supervised-learning row is **not automatically one session**. The offline
builder groups all reliable sessions from the same user, task, and recurring
occurrence, then emits one row only after that task occurrence is complete.

This avoids teaching a task-duration model that a 25-minute Pomodoro is the full
duration of a task that actually needed several sessions.

```text
task prediction
  -> session 1 (10 active minutes, incomplete)
  -> session 2 (20 active minutes, task completed)
  -> one task outcome with actual_active_duration_minutes = 30
```

## Identifier and privacy boundary

`focusbuddy_states.user_id` is the existing Supabase Auth UUID. It is added by
the offline export join; it is not duplicated in every record inside the state
JSON. This supports user-grouped evaluation without adding a name, email, phone
number, Google profile, or payment data.

Task text is needed by the Duration model and can itself contain user-written
content. Therefore raw exports are restricted training inputs. Aggregate reports
must show counts and metrics, never task text or user IDs.

## Runtime session record: `focus-outcome-v1`

| Field | Source | Purpose |
|---|---|---|
| `schema_version` | constant | Allows backward-compatible parsing. |
| `record_id` | UUID at Focus start | Detects duplicate records. |
| `session_id` | UUID at Focus start | Joins all lifecycle updates for one session. |
| `task_id`, `step_id`, `occurrence_date` | selected task/step | Preserves task and recurring-occurrence identity. |
| `task_text`, `category` | task snapshot | Features and provenance if a task is later removed. |
| `importance` | input used when prediction was made | Preserves the actual prediction feature. |
| `has_deadline`, `deadline_days_or_zero` | task/prediction snapshot | Separates no deadline from deadline today. |
| `predicted_duration_minutes` | `duration_prediction` on task | Original task estimate; never the observed target. |
| `prediction_model_version`, `prediction_source` | task prediction metadata | Reproduces which runtime predictor produced the estimate. |
| `global_prediction_minutes`, `global_model_version` | Global Duration inference | Preserves population estimate separately from the final personalized value. |
| `global_dataset_version`, `global_artifact_sha256` | promoted artifact metadata | Identifies the immutable Global Model source when available. |
| `personalization_version`, `personalization_dataset_version` | per-user calibration state | Shows whether/which precomputed calibration changed the Global prediction. |
| `planned_session_minutes` | Focus start/update | Distinguishes session plan from full task estimate. |
| `task_created_at`, `started_at`, `ended_at`, `created_at` | task and Focus lifecycle | Temporal provenance and validation. |
| `actual_active_duration_minutes` | unpaused Focus countdown | Measured target contribution for this session. |
| `pause_duration_minutes` | explicit pause/resume events | Audit of active versus elapsed time. |
| `interruption_count` | number of explicit pauses | Session context; not silently inferred. |
| `completion_status`, `outcome`, `task_completed` | explicit Focus outcome and Tracker update | Determines whether a complete task label exists. |
| `task_snapshot_captured` | Focus start join | Proves a task relationship existed at collection time. |
| `timing_quality` | collector capability | Records the current pause-aware/no-visibility limitation. |
| `data_provenance` | task provenance | `real_user`, `synthetic_scenario`, or `synthetic_fixture`; this is the training boundary. |
| `collection_context` | runtime context | `setting_demo` or `production`; context alone does not make genuine usage synthetic. |
| `is_demo`, `synthetic` | compatibility flags | Derived for legacy readers; synthetic scenarios/fixtures remain excluded. |
| `data_quality_status`, `data_quality_reason` | runtime placeholder, replaced offline | Preserves why a row is valid, suspicious, invalid, or unknown. |

The Supabase envelope contributes `user_id` and the offline builder contributes
`dataset_version`, `task_association_valid`, and derived eligibility fields.

## Estimated versus actual duration

- `predicted_duration_minutes`: full-task estimate available before work begins.
- `planned_session_minutes`: length selected for one Focus block.
- `actual_active_duration_minutes`: countdown time consumed while the session was
  not explicitly paused.
- `pause_duration_minutes`: explicit paused time, excluded from active duration.
- Wall-clock elapsed is `ended_at - started_at`; it is not used as the target.

The current web app has no browser visibility signal. An unpaused background tab
therefore cannot be distinguished from a user intentionally continuing the task
outside the visible tab. The schema states that limitation instead of inventing
attention data.

## Quality and label rules

`valid` means identity, task relationship, prediction provenance, explicit data
provenance, timestamps, and positive pause-aware measurement are internally
consistent. A `real_user` row must receive a valid Supabase Auth UUID from the
export envelope. `suspicious` means review is required, currently for sessions
over 8 hours. `invalid` covers missing/legacy-ambiguous provenance, corrupted
identity, duplicated IDs, test records, missing prediction or model version,
invalid timestamps, non-positive duration, active time longer than elapsed time,
and durations over 24 hours. `unknown` covers unfinished, crashed, abandoned, or
explicitly unreliable timing.

Phase 7 additionally requires a non-empty prediction source, positive planned
session duration, explicit collection context, and runtime quality placeholders.
For one task occurrence, every contributing session must preserve the same final
prediction, Global prediction/version, prediction source, and personalization
version. A mismatch rejects the whole group instead of guessing which prediction
was actually shown.

A valid session measurement still is not necessarily a task-duration label. A
training row requires a final `outcome=completed`, `task_completed=true`, and a
complete valid history for that task occurrence. Synthetic rows can exercise the
pipeline but always retain `training_eligible=false`.

Setting Demo is not a synthetic label. A person using the normal flow while demo
tools are enabled produces `real_user` data with
`collection_context=setting_demo`. Only developer-created scenario tasks and
fixtures receive synthetic provenance.

## Versioned aggregate training row

The `focusbuddy-user-outcomes-v1` row contains:

- `record_id`, `user_id`, `task_id`, final `session_id`;
- `source_session_ids` and `task_family_id`;
- task text/category/importance/deadline fields;
- predicted duration and prediction model version;
- first start, final end, and summed actual active duration;
- summed pause/interruption values;
- completion, quality, dataset version, and synthetic/eligibility provenance.

The target is `actual_active_duration_minutes`. Source identifiers remain in the
restricted dataset for leakage-safe splitting and audits, not as model features.

Personalization state is separate from this label row. It is associated with one
Supabase Auth UUID, requires 30 eligible completed outcomes across at least 14
active days and 3 categories, and may use only outcomes ending before the next
prediction cutoff. The current task outcome can never change its own prediction.
