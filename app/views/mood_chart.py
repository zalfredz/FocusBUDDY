"""Grafik mood bulanan -- upgrade opsional di samping bar chart 7-hari.

CATATAN PENTING: `ft.LineChart` yang disebut di dokumen rencana 3.0 TERNYATA
NGGAK ADA di Flet 0.86.4 yang kepakai di project ini (dicek langsung lewat
`dir(ft)` -- nggak ada satupun kelas *Chart). Solusinya dibangun manual
pakai `flet.canvas` (Path/Points/Circle), yang emang ada di versi ini.

Warnanya ngikut SCORE_COLORS yang udah ada di mood.py -- nggak bikin skema
warna baru sendiri.
"""
from __future__ import annotations

import calendar

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


def _y_for_score(score: float) -> float:
    """Skor 1-5 -> koordinat y kanvas (1 di bawah, 5 di atas)."""
    plot_h = CHART_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    ratio = (score - 1) / 4  # 0..1
    return CHART_HEIGHT - MARGIN_BOTTOM - ratio * plot_h


def _x_for_day(day: int, days_in_month: int) -> float:
    plot_w = CHART_WIDTH - 2 * MARGIN_X
    if days_in_month <= 1:
        return MARGIN_X
    return MARGIN_X + (day - 1) / (days_in_month - 1) * plot_w


def build_month_chart(logs: list[dict], year: int, month: int, score_colors: dict) -> ft.Control:
    """logs: SEMUA mood_logs (belum difilter). Filter+plot cuma yang tanggalnya
    di bulan `year`-`month`. Hari tanpa catatan dilewatin -- garis nyambung
    lurus ke titik berikutnya yang beneran ada datanya, nggak dikarang."""
    days_in_month = calendar.monthrange(year, month)[1]
    month_logs = sorted(
        (log for log in logs if log["date"].startswith(f"{year:04d}-{month:02d}")),
        key=lambda log: log["date"],
    )

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

    # Area di bawah garis -- fill tipis, warna dari titik terakhir (paling
    # relevan/terbaru) biar nggak perlu bikin gradient.
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

    # Garis penghubung.
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

    # Label sumbu-x: tanggal 1, tengah, akhir bulan -- cukup buat orientasi,
    # nggak perlu satu-satu (bakal numpuk di layar sekecil ini).
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
