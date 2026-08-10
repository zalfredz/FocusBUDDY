"""Kontrak kecil untuk menilai kualitas keputusan Kalem.

Modul ini sengaja belum memilih tugas atau mengubah UI. Ia mendefinisikan
fakta yang harus benar sebelum Tracker berani membuat rencana: berapa beban
yang diketahui, apakah muat di waktu yang tersedia, dan seberapa besar
overflow-nya. Dengan begitu skenario kualitas bisa diuji tanpa AI/Flet.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapacityAssessment:
    available_minutes: int
    estimated_minutes: int
    unknown_tasks: int
    overflow_minutes: int

    @property
    def fits(self) -> bool:
        return self.overflow_minutes <= 0

    @property
    def utilization(self) -> float:
        if self.available_minutes <= 0:
            return 0.0
        return self.estimated_minutes / self.available_minutes


def assess_capacity(tasks: list[dict], available_minutes: int) -> CapacityAssessment:
    """Bandingkan beban tugas terbuka dengan waktu yang benar-benar tersedia.

    Tugas tanpa `menit_est` tidak diberi angka palsu; jumlahnya dilaporkan
    sebagai ketidakpastian. Ini penting karena "muat" dengan dua tugas tanpa
    estimasi bukan keputusan yang jujur.
    """
    available = max(0, int(available_minutes or 0))
    known = 0
    unknown = 0
    for task in tasks:
        if all(step.get("done") for step in task.get("steps", [])) and task.get("steps"):
            continue
        try:
            estimate = int(task.get("menit_est") or 0)
        except (TypeError, ValueError):
            estimate = 0
        if estimate > 0:
            known += estimate
        else:
            unknown += 1
    return CapacityAssessment(
        available_minutes=available,
        estimated_minutes=known,
        unknown_tasks=unknown,
        overflow_minutes=max(0, known - available),
    )
