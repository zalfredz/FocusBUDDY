"""Stable inference boundary for Global Duration + per-user calibration."""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from models import model_durasi
from models.personalization import DurationPersonalizationState, state_for_user


def apply_duration_personalization(
    global_prediction: model_durasi.Perkiraan,
    personalization: DurationPersonalizationState,
) -> model_durasi.Perkiraan:
    """Apply a precomputed state without fitting or mutating shared state."""
    global_minutes = global_prediction.global_minutes or global_prediction.menit
    if not personalization.active:
        return replace(
            global_prediction,
            global_minutes=global_minutes,
            personalization_version="",
            personalization_dataset_version="",
            personalization_active=False,
        )
    factor = personalization.factor
    lower = max(5, min(round(global_prediction.bawah * factor), 300))
    minutes = max(5, min(round(global_prediction.menit * factor), 300))
    upper = max(5, min(round(global_prediction.atas * factor), 300))
    lower, minutes, upper = sorted((lower, minutes, upper))
    return replace(
        global_prediction,
        menit=minutes,
        bawah=lower,
        atas=upper,
        sumber="global_plus_personal_calibration",
        catatan=(
            f"Perkiraan global disesuaikan dari {personalization.eligible_outcome_count} "
            "hasil tugas kamu sebelumnya."
        ),
        faktor_personal=factor,
        global_minutes=global_minutes,
        personalization_version=personalization.version,
        personalization_dataset_version=personalization.source_dataset_version,
        personalization_active=True,
    )


class DurationPredictionService:
    @property
    def categories(self) -> dict[str, dict[str, str]]:
        return model_durasi.KATEGORI

    def unit_for_category(self, key: str) -> str:
        return model_durasi.satuan_kategori(key)

    def predict(
        self,
        title: str,
        *,
        deadline_days: float = 7,
        importance: float = 5,
        category: str = "",
        quantity: float = 0,
        focus_records: Optional[list[dict]] = None,
        calibration: Optional[float] = None,
        energy: Optional[int] = None,
        user_id: str = "",
        personalization_payload: Optional[dict] = None,
        allow_test_personalization: bool = False,
    ) -> model_durasi.Perkiraan:
        global_prediction = model_durasi.perkirakan(
            title,
            tempo_hari=deadline_days,
            penting=importance,
            kategori=category,
            jumlah=quantity,
            records=[],
            kalibrasi=1.0,
            energi=energy,
        )
        if personalization_payload is None:
            from app import storage

            user_id = user_id or storage.current_user_id()
            personalization_payload = storage.get_duration_personalization()
        state = state_for_user(
            personalization_payload,
            expected_user_id=user_id,
            allow_test_state=allow_test_personalization,
        )
        return apply_duration_personalization(global_prediction, state)

    def status(self) -> dict:
        return model_durasi.status()


duration_predictions = DurationPredictionService()
