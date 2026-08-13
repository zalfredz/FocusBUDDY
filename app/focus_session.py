"""State sesi fokus yang terisolasi per browser."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from app import session_scope

_SESSION_KEY = "focusbuddy.focus_session.v1"


@dataclass
class _FocusState:
    total_seconds: int = 0
    task_estimate_minutes: int = 0
    label: str = ""
    task_title: str = ""
    ends_at: Optional[datetime] = None
    paused_left: Optional[int] = None
    finished: bool = False
    kategori: str = ""
    jumlah_unit: float = 0.0
    energi: int = 4
    recorded: bool = False
    task_id: str = ""
    step_id: str = ""
    occurrence_date: str = ""
    step_index: int = -1
    decision_id: str = ""
    started_at: str = ""
    session_id: str = ""
    interruption_count: int = 0
    pause_duration_seconds: float = 0.0
    paused_at: Optional[datetime] = None


_FALLBACK_STATE = _FocusState()


def _state() -> _FocusState:
    return session_scope.get_or_create(_SESSION_KEY, _FocusState) or _FALLBACK_STATE


def start(
    minutes: int,
    label: str = "",
    task_title: str = "",
    kategori: str = "",
    jumlah_unit: float = 0,
    energi: int = 4,
    task_id: str = "",
    step_id: str = "",
    occurrence_date: str = "",
    step_index: int = -1,
    decision_id: str = "",
    task_estimate_minutes: int = 0,
) -> None:
    state = _state()
    state.total_seconds = max(int(minutes), 1) * 60
    state.task_estimate_minutes = max(int(task_estimate_minutes or 0), 0)
    state.label = label
    state.task_title = task_title
    started = datetime.now()
    state.ends_at = started + timedelta(seconds=state.total_seconds)
    state.paused_left = None
    state.finished = False
    state.kategori = kategori
    state.jumlah_unit = float(jumlah_unit)
    state.energi = int(energi)
    state.recorded = False
    state.task_id = task_id
    state.step_id = step_id
    state.occurrence_date = occurrence_date
    state.step_index = int(step_index)
    state.decision_id = decision_id
    state.started_at = started.isoformat()
    state.session_id = str(uuid.uuid4())
    state.interruption_count = 0
    state.pause_duration_seconds = 0.0
    state.paused_at = None
    if decision_id:
        from app import storage

        storage.record_decision_started(
            decision_id, planned_focus_minutes=state.total_seconds // 60
        )
    from app import storage

    storage.start_focus_outcome_record(
        session_id=state.session_id,
        task_id=state.task_id,
        step_id=state.step_id,
        occurrence_date=state.occurrence_date,
        planned_session_minutes=state.total_seconds // 60,
        task_title=state.task_title,
    )


def elapsed_minutes() -> float:
    state = _state()
    return max(0.0, (state.total_seconds - remaining()) / 60.0)


def record_if_worthwhile(
    outcome: str = "",
    reflection: str = "",
) -> Optional[dict]:
    from app import storage

    state = _state()
    if state.recorded or state.total_seconds <= 0:
        return None
    state.recorded = True
    ended_at = datetime.now().isoformat()
    active_minutes = elapsed_minutes()
    pause_minutes = _pause_seconds_including_current() / 60.0
    task_completed = storage.task_completion_status(
        state.task_id, state.occurrence_date or None
    )
    record = storage.add_focus_record(
        kategori=state.kategori,
        jumlah_unit=state.jumlah_unit,
        menit=active_minutes,
        energi=state.energi,
        task_title=state.task_title,
        menit_est=state.total_seconds // 60,
        task_estimate_minutes=state.task_estimate_minutes,
        selesai=outcome == "completed",
        outcome=outcome,
        task_id=state.task_id,
        step_id=state.step_id,
        occurrence_date=state.occurrence_date,
        step_index=state.step_index if state.step_index >= 0 else None,
        decision_id=state.decision_id,
        reflection=reflection,
        session_id=state.session_id,
        session_started_at=state.started_at,
        session_ended_at=ended_at,
        task_completed=task_completed,
        interruption_count=state.interruption_count,
        pause_duration_minutes=pause_minutes,
    )
    completion_status = (
        "task_completed"
        if outcome == "completed" and task_completed
        else "step_completed"
        if outcome == "completed"
        else outcome or "ended_without_outcome"
    )
    storage.update_focus_outcome_record(
        state.session_id,
        ended_at=ended_at,
        actual_active_duration_minutes=round(active_minutes, 4),
        pause_duration_minutes=round(pause_minutes, 4),
        completion_status=completion_status,
        outcome=outcome,
        interruption_count=state.interruption_count,
        task_completed=task_completed,
        data_quality_status="unknown",
        data_quality_reason="pending_offline_validation",
    )
    return record


def pause() -> None:
    state = _state()
    if state.ends_at is None:
        return
    state.paused_left = remaining()
    state.ends_at = None
    state.paused_at = datetime.now()
    state.interruption_count += 1
    from app import storage

    storage.update_focus_outcome_record(
        state.session_id,
        completion_status="paused",
        interruption_count=state.interruption_count,
        pause_duration_minutes=round(state.pause_duration_seconds / 60.0, 4),
    )


def resume() -> None:
    state = _state()
    if state.paused_left is None or state.paused_left <= 0:
        return
    resumed_at = datetime.now()
    if state.paused_at is not None:
        state.pause_duration_seconds += max(
            0.0, (resumed_at - state.paused_at).total_seconds()
        )
    state.ends_at = resumed_at + timedelta(seconds=state.paused_left)
    state.paused_left = None
    state.paused_at = None
    from app import storage

    storage.update_focus_outcome_record(
        state.session_id,
        completion_status="started",
        interruption_count=state.interruption_count,
        pause_duration_minutes=round(state.pause_duration_seconds / 60.0, 4),
    )


def reset() -> None:
    state = _state()
    state.ends_at = None
    state.paused_left = state.total_seconds
    state.finished = False


def update_duration(minutes: int) -> bool:
    """Ubah durasi sesi aktif tanpa mengulang waktu yang sudah dijalani."""
    state = _state()
    if not is_active() or state.finished:
        return False
    try:
        new_total = int(minutes) * 60
    except (TypeError, ValueError):
        return False
    if not 60 <= new_total <= 30 * 60:
        return False

    left = remaining()
    elapsed = max(0, state.total_seconds - left)
    if new_total <= elapsed:
        return False

    new_left = new_total - elapsed
    running = state.ends_at is not None
    state.total_seconds = new_total
    if running:
        state.ends_at = datetime.now() + timedelta(seconds=new_left)
        state.paused_left = None
    else:
        state.ends_at = None
        state.paused_left = new_left
    from app import storage

    storage.update_focus_outcome_record(
        state.session_id,
        planned_session_minutes=new_total // 60,
    )
    return True


def stop() -> None:
    """Buang sesi tanpa menyimpulkan outcome; dipakai logout dan cleanup."""
    _clear()


def finish(outcome: str, reflection: str = "") -> Optional[dict]:
    """Simpan outcome eksplisit lalu tutup sesi fokus."""
    allowed = {"completed", "incomplete", "blocked", "later", "rest"}
    if outcome not in allowed or not is_active():
        return None
    from app import storage

    state = _state()
    if outcome == "completed":
        storage.apply_focus_outcome(
            state.task_id,
            state.step_index,
            outcome,
            state.occurrence_date or None,
        )
    record = record_if_worthwhile(outcome, reflection)
    storage.record_decision_outcome(
        state.decision_id,
        outcome=outcome,
        completed=outcome == "completed",
        actual_focus_minutes=(record or {}).get("actual_focus_minutes", 0),
        planned_focus_minutes=state.total_seconds // 60,
    )
    _clear()
    return record


def complete_and_continue(
    expected_started_at: str = "",
) -> tuple[Optional[dict], bool]:
    """Selesaikan step aktif dan lanjut otomatis jika parent task masih sama."""
    if not is_active():
        return None, False
    if expected_started_at and _state().started_at != expected_started_at:
        return None, False

    from app import storage
    from app.core import kalem_engine

    current = snapshot()
    record = finish("completed")
    pending = storage.next_pending_task_step(
        current["task_id"], current["occurrence_date"] or None
    )
    if pending is None:
        return record, False

    task, step_index, step = pending
    minutes, remaining_estimate = kalem_engine.task_focus_minutes(
        task,
        step_index,
        current["energi"],
        storage.get_focus_records(),
    )
    start(
        minutes,
        label=step.get("text", task.get("title", "Sesi fokus")),
        task_title=task.get("title", current["task_title"]),
        kategori=task.get("kategori", current["kategori"]),
        jumlah_unit=task.get("jumlah_unit", current["jumlah_unit"]),
        energi=current["energi"],
        task_id=current["task_id"],
        step_id=str(step.get("id", "")),
        occurrence_date=current["occurrence_date"],
        step_index=step_index,
        task_estimate_minutes=remaining_estimate,
    )
    return record, True


def _clear() -> None:
    state = _state()
    state.total_seconds = 0
    state.task_estimate_minutes = 0
    state.label = ""
    state.task_title = ""
    state.ends_at = None
    state.paused_left = None
    state.finished = False
    state.kategori = ""
    state.jumlah_unit = 0.0
    state.energi = 4
    state.recorded = False
    state.task_id = ""
    state.step_id = ""
    state.occurrence_date = ""
    state.step_index = -1
    state.decision_id = ""
    state.started_at = ""
    state.session_id = ""
    state.interruption_count = 0
    state.pause_duration_seconds = 0.0
    state.paused_at = None


def _pause_seconds_including_current() -> float:
    state = _state()
    total = state.pause_duration_seconds
    if state.paused_at is not None:
        total += max(0.0, (datetime.now() - state.paused_at).total_seconds())
    return total


def remaining() -> int:
    state = _state()
    if state.ends_at is not None:
        return max(0, int((state.ends_at - datetime.now()).total_seconds()))
    if state.paused_left is not None:
        return max(0, state.paused_left)
    return state.total_seconds


def is_running() -> bool:
    return _state().ends_at is not None and remaining() > 0


def is_paused() -> bool:
    state = _state()
    return state.paused_left is not None and state.paused_left > 0


def is_active() -> bool:
    return _state().total_seconds > 0


def just_finished() -> bool:
    state = _state()
    if state.total_seconds > 0 and remaining() <= 0 and state.ends_at is not None:
        _ends_at_none()
        state.finished = True
    return state.finished


def _ends_at_none() -> None:
    state = _state()
    state.ends_at = None
    state.paused_left = 0


def progress() -> float:
    state = _state()
    if state.total_seconds <= 0:
        return 0.0
    return max(0.0, min(1.0, remaining() / state.total_seconds))


def snapshot() -> dict[str, Any]:
    just_finished()
    state = _state()
    left = remaining()
    return {
        "kategori": state.kategori,
        "jumlah_unit": state.jumlah_unit,
        "energi": state.energi,
        "total_seconds": state.total_seconds,
        "task_estimate_minutes": state.task_estimate_minutes,
        "remaining": left,
        "label": state.label,
        "task_title": state.task_title,
        "task_id": state.task_id,
        "step_id": state.step_id,
        "occurrence_date": state.occurrence_date,
        "step_index": state.step_index,
        "decision_id": state.decision_id,
        "session_started_at": state.started_at,
        "session_id": state.session_id,
        "interruption_count": state.interruption_count,
        "pause_duration_minutes": round(_pause_seconds_including_current() / 60.0, 4),
        "running": is_running(),
        "paused": is_paused(),
        "active": is_active(),
        "finished": state.total_seconds > 0 and left <= 0,
        "progress": progress(),
        "clock": fmt(left),
    }


def fmt(seconds: int) -> str:
    m, s = divmod(max(int(seconds), 0), 60)
    return f"{m:02d}:{s:02d}"
