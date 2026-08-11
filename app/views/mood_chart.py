"""Renderer grafik mood bulanan."""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date

import flet as ft
import flet.canvas as cv

from app import clock, theme

CHART_WIDTH = 300.0
CHART_HEIGHT = 130.0
MARGIN_X = 14.0
MARGIN_TOP = 10.0
MARGIN_BOTTOM = 10.0

MONTH_NAMES = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

MIN_CHECKINS_FOR_COMPARISON = 3
MIN_PER_GROUP = 2


@dataclass(frozen=True)
class MonthSummary:
    checkin_days: int
    average: float | None
    previous_days: int
    previous_average: float | None
    comparison: str = ""
    insights: list[str] = field(default_factory=list)


def _logs_for_month(logs: list[dict], year: int, month: int) -> list[dict]:
    by_day: dict[str, dict] = {}
    for log in logs:
        raw_date = str(log.get("date", ""))
        try:
            parsed_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if (
            parsed_date.year == year
            and parsed_date.month == month
            and isinstance(log.get("score"), (int, float))
        ):
            by_day.setdefault(raw_date, log)
    return sorted(by_day.values(), key=lambda log: str(log["date"]))


def analyse_month(logs: list[dict], year: int, month: int) -> MonthSummary:
    current = _logs_for_month(logs, year, month)
    previous_year, previous_month = shift_month(year, month, -1)
    previous = _logs_for_month(logs, previous_year, previous_month)
    average = (
        sum(float(log["score"]) for log in current) / len(current)
        if current
        else None
    )
    previous_average = (
        sum(float(log["score"]) for log in previous) / len(previous)
        if previous
        else None
    )

    comparison = ""
    if (
        average is not None
        and previous_average is not None
        and len(current) >= MIN_CHECKINS_FOR_COMPARISON
        and len(previous) >= MIN_CHECKINS_FOR_COMPARISON
    ):
        difference = average - previous_average
        previous_name = MONTH_NAMES[previous_month - 1]
        if abs(difference) < 0.25:
            comparison = f"Rata-ratanya relatif sama dengan {previous_name}."
        elif difference > 0:
            comparison = (
                f"Rata-rata {difference:.1f} poin lebih tinggi dibanding {previous_name}."
            )
        else:
            comparison = (
                f"Rata-rata {abs(difference):.1f} poin lebih rendah dibanding {previous_name}."
            )

    insights: list[str] = []
    if len(current) >= 2:
        highest = max(current, key=lambda log: float(log["score"]))
        lowest = min(current, key=lambda log: float(log["score"]))
        if float(highest["score"]) > float(lowest["score"]):
            insights.append(
                f"Mood tertinggi tercatat tanggal {int(str(highest['date'])[-2:])} "
                f"({float(highest['score']):g}/5), terendah tanggal "
                f"{int(str(lowest['date'])[-2:])} ({float(lowest['score']):g}/5)."
            )

    weekday = [float(log["score"]) for log in current if not _is_weekend(log)]
    weekend = [float(log["score"]) for log in current if _is_weekend(log)]
    if len(weekday) >= MIN_PER_GROUP and len(weekend) >= MIN_PER_GROUP:
        gap = sum(weekend) / len(weekend) - sum(weekday) / len(weekday)
        if gap >= 0.5:
            insights.append("Mood bulan ini cenderung lebih tinggi saat weekend.")
        elif gap <= -0.5:
            insights.append("Mood bulan ini cenderung lebih tinggi saat hari kerja.")
        else:
            insights.append("Mood bulan ini relatif serupa antara hari kerja dan weekend.")

    low_energy = [
        float(log["score"])
        for log in current
        if isinstance(log.get("energy"), (int, float)) and float(log["energy"]) <= 2
    ]
    high_energy = [
        float(log["score"])
        for log in current
        if isinstance(log.get("energy"), (int, float)) and float(log["energy"]) >= 4
    ]
    if len(low_energy) >= MIN_PER_GROUP and len(high_energy) >= MIN_PER_GROUP:
        gap = sum(high_energy) / len(high_energy) - sum(low_energy) / len(low_energy)
        if gap >= 0.5:
            insights.append("Mood tercatat lebih rendah saat energi berada di level 1–2.")

    return MonthSummary(
        checkin_days=len(current),
        average=average,
        previous_days=len(previous),
        previous_average=previous_average,
        comparison=comparison,
        insights=insights,
    )


def _is_weekend(log: dict) -> bool:
    if log.get("is_weekend") is not None:
        return bool(log["is_weekend"])
    try:
        return date.fromisoformat(str(log.get("date", ""))).weekday() >= 5
    except ValueError:
        return False


def build_month_summary(logs: list[dict], year: int, month: int) -> ft.Control:
    summary = analyse_month(logs, year, month)
    average = f"{summary.average:.1f}/5" if summary.average is not None else "—"
    children: list[ft.Control] = [
        ft.Row(
            [
                _stat("Rata-rata mood", average),
                _stat("Hari check-in", str(summary.checkin_days)),
            ],
            spacing=8,
        )
    ]
    if summary.checkin_days < MIN_CHECKINS_FOR_COMPARISON:
        children.append(
            ft.Text(
                "Belum cukup data untuk melihat pola bulan ini. Minimal 3 hari check-in.",
                size=11.5,
                color=theme.MUTED,
            )
        )
    elif summary.comparison:
        children.append(ft.Text(summary.comparison, size=11.5, color=theme.ON_BACKGROUND))
    else:
        children.append(
            ft.Text(
                "Perbandingan periode sebelumnya muncul setelah masing-masing punya "
                "minimal 3 hari check-in.",
                size=11.5,
                color=theme.MUTED,
            )
        )
    for insight in summary.insights:
        children.append(
            ft.Row(
                [
                    ft.Icon(ft.Icons.CIRCLE, size=6, color=theme.PRIMARY),
                    ft.Text(insight, size=11.5, color=theme.MUTED, expand=True),
                ],
                spacing=7,
                vertical_alignment=ft.CrossAxisAlignment.START,
            )
        )
    return ft.Column(children, spacing=7)


def _stat(label: str, value: str) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(value, size=17, weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND),
                ft.Text(label, size=10.5, color=theme.MUTED),
            ],
            spacing=1,
        ),
        expand=True,
        padding=10,
        bgcolor=theme.BACKGROUND,
        border_radius=10,
    )


def _y_for_score(score: float) -> float:
    plot_h = CHART_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    ratio = (score - 1) / 4
    return CHART_HEIGHT - MARGIN_BOTTOM - ratio * plot_h


def _x_for_day(day: int, days_in_month: int) -> float:
    plot_w = CHART_WIDTH - 2 * MARGIN_X
    if days_in_month <= 1:
        return MARGIN_X
    return MARGIN_X + (day - 1) / (days_in_month - 1) * plot_w


def build_month_chart(logs: list[dict], year: int, month: int, score_colors: dict) -> ft.Control:
    days_in_month = calendar.monthrange(year, month)[1]
    month_logs = _logs_for_month(logs, year, month)

    if not month_logs:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Icon(ft.Icons.SHOW_CHART, size=28, color=theme.BORDER),
                    ft.Text("Nggak ada catatan bulan ini.", size=12, color=theme.MUTED),
                ],
                spacing=6,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            height=CHART_HEIGHT,
            alignment=ft.Alignment.CENTER,
        )

    points: list[ft.Offset] = []
    dots: list[cv.Shape] = []
    for log in month_logs:
        day = int(log["date"][-2:])
        x = _x_for_day(day, days_in_month)
        y = _y_for_score(log["score"])
        points.append(ft.Offset(x, y))
        dots.append(
            cv.Circle(
                x, y, radius=4,
                paint=ft.Paint(color=score_colors.get(log["score"], theme.MUTED), style=ft.PaintingStyle.FILL),
            )
        )

    shapes: list[cv.Shape] = []

    baseline_y = CHART_HEIGHT - MARGIN_BOTTOM
    area_color = score_colors.get(month_logs[-1]["score"], theme.PRIMARY)
    area_elements: list[cv.Path.PathElement] = [cv.Path.MoveTo(points[0].x, baseline_y)]
    for p in points:
        area_elements.append(cv.Path.LineTo(p.x, p.y))
    area_elements.append(cv.Path.LineTo(points[-1].x, baseline_y))
    area_elements.append(cv.Path.Close())
    shapes.append(
        cv.Path(
            elements=area_elements,
            paint=ft.Paint(color=ft.Colors.with_opacity(0.16, area_color), style=ft.PaintingStyle.FILL),
        )
    )

    if len(points) > 1:
        shapes.append(
            cv.Points(
                points=points,
                point_mode=cv.PointMode.POLYGON,
                paint=ft.Paint(
                    color=theme.PRIMARY,
                    stroke_width=2.5,
                    style=ft.PaintingStyle.STROKE,
                    stroke_cap=ft.StrokeCap.ROUND,
                ),
            )
        )

    shapes.extend(dots)

    canvas = cv.Canvas(shapes=shapes, width=CHART_WIDTH, height=CHART_HEIGHT)

    axis_labels = ft.Row(
        [
            ft.Text("1", size=9, color=theme.MUTED),
            ft.Text(str(days_in_month // 2), size=9, color=theme.MUTED),
            ft.Text(str(days_in_month), size=9, color=theme.MUTED),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    return ft.Column(
        [
            ft.Container(content=canvas, alignment=ft.Alignment.CENTER),
            axis_labels,
        ],
        spacing=4,
    )


def month_nav(year: int, month: int, on_prev, on_next) -> ft.Row:
    return ft.Row(
        [
            ft.IconButton(icon=ft.Icons.CHEVRON_LEFT, icon_size=18, icon_color=theme.MUTED, on_click=on_prev),
            ft.Text(
                f"{MONTH_NAMES[month - 1]} {year}",
                size=12.5,
                weight=ft.FontWeight.BOLD,
                color=theme.ON_BACKGROUND,
                expand=True,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.IconButton(icon=ft.Icons.CHEVRON_RIGHT, icon_size=18, icon_color=theme.MUTED, on_click=on_next),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
    )


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    idx = (year * 12 + (month - 1)) + delta
    return idx // 12, idx % 12 + 1


def today_year_month() -> tuple[int, int]:
    t = clock.today()
    return t.year, t.month
