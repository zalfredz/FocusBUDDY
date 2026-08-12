# ML Outcome Data Flow

## Current flow before Phase 3

```text
Tracker task form
  -> models/model_durasi.py:perkirakan()
  -> storage.add_task(menit_est)
  -> Home/Tracker selects task and Focus duration
  -> focus_session.start()
  -> in-memory/session timer
  -> pause/resume or explicit outcome
  -> storage.add_focus_record()
  -> storage.save_state()
  -> Supabase focusbuddy_states.state JSON
```

The existing `focus_records` already preserve task/step identity, timestamps,
outcome, and active minutes at session end. They do not persist the session at
start, do not preserve prediction-model provenance, and cannot reveal a crash or
abandoned session because no end record exists.

## Proposed and implemented collection flow

```text
TASK CREATED
  Tracker obtains Global Duration prediction
  -> optionally applies eligible precomputed state for the current Auth UUID
  -> task.duration_prediction stores global + personalization provenance

FOCUS STARTED
  focus_session.start()
  -> session UUID + task/prediction snapshot
  -> ml_outcome_records append unfinished focus-outcome-v1
  -> save_state -> existing Supabase sync hook

FOCUS PAUSED / RESUMED / DURATION CHANGED
  existing controls
  -> same materialized record updated
  -> interruption count, pause duration, planned session updated

FOCUS ENDED
  explicit completed/incomplete/blocked/later/rest outcome
  -> existing task and focus_records behavior
  -> same outcome record finalized with active time and completion state

OFFLINE ONLY
  restricted Supabase JSON export
  -> join user envelope + task + session snapshot
  -> quality validator
  -> aggregate complete task-occurrence history
  -> versioned training candidates
  -> future reviewed personalization state for that same user UUID
```

There is no second generic analytics/event bus. Phase 3 reuses the Focus
lifecycle, `storage.save_state()`, the per-user Supabase row, and existing task
identity. `ml_outcome_records` is a purpose-specific materialized session log
because an end-only `focus_record` cannot represent unfinished sessions.

The Phase 6 personalization builder is also offline. Runtime applies a bounded,
versioned state but never derives it from the outcome currently being recorded.

## Event contract

| Event | Code source | Timestamp/fields | Relation | Label contribution |
|---|---|---|---|---|
| `task_created` | `tracker.open_add_task()` -> `storage.add_task()` | task ID/text, prediction metadata, created time | parent task | Prediction/features only. |
| `focus_started` | `focus_session.start()` | session/task/step IDs, task snapshot, started time, planned minutes | task occurrence + session | Creates an unfinished record; no label yet. |
| `focus_paused` | `focus_session.pause()` | interruption count, current pause state | same session ID | Freezes active countdown; no label yet. |
| `focus_resumed` | `focus_session.resume()` | accumulated explicit pause duration | same session ID | Preserves active/elapsed distinction. |
| `focus_duration_changed` | `focus_session.update_duration()` | revised planned session minutes | same session ID | Context only; does not alter task prediction. |
| `focus_completed` | `focus_session.finish("completed")` | ended time, active time, explicit outcome | same session and task/step | Contributes measured time; final label only if task complete. |
| `focus_cancelled/resolved` | other explicit Focus outcomes | ended time, active time, outcome | same session | Measurement may be usable but is not alone a task label. |
| `task_completed` | `storage.apply_focus_outcome()` | Tracker step/task completion | task occurrence | Opens aggregate task-label eligibility. |

## Persistence and Supabase

`storage.save_state()` writes the session-isolated local cache and invokes the
existing cloud save hook. `FocusBuddyCloud.enqueue_state(user.id, state)` uploads
the same state to the authenticated user's `focusbuddy_states` row. Row-level
user separation remains the existing Supabase Auth UUID and RLS boundary.

No name, email, or phone is added to the outcome records. The offline join takes
`user_id` from the Supabase row envelope. A reset/delete of the user's state also
removes the embedded outcome list on the next cloud upsert; Phase 3 creates no
additional cloud table with a second retention path.

## Failure behavior

- Explicit finish: record is finalized and can be validated.
- Explicit pause: active time stops; pause time is separately accumulated.
- App closes/crashes after start: unfinished record remains without end/active
  duration and is classified `unknown`, never zero.
- Legacy task without prediction version: future session is retained but marked
  invalid for training rather than assigned a guessed model version.
- Normal use while Setting Demo is enabled: record carries
  `data_provenance=real_user`; `collection_context=setting_demo` is informational.
- Demo-overlay task: record carries `data_provenance=synthetic_scenario` and is
  excluded from training even if its other measurements are structurally valid.
- Legacy outcome without explicit provenance is invalid rather than silently
  assumed real.
