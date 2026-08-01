"""Komponen UI kecil yang dipakai berulang di banyak halaman."""
from __future__ import annotations

from typing import Optional

import flet as ft

from app import theme


def card(content: ft.Control, bgcolor: str = theme.SURFACE, padding: int = 20) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=bgcolor,
        border_radius=theme.CARD_RADIUS,
        padding=padding,
        border=ft.Border.all(1, theme.BORDER),
    )


def title(text: str, size: int = 20) -> ft.Text:
    return ft.Text(
        text,
        size=size,
        weight=ft.FontWeight.BOLD,
        color=theme.ON_BACKGROUND,
        font_family=theme.FONT_DISPLAY,
    )


def subtitle(text: str, size: int = 13) -> ft.Text:
    return ft.Text(text, size=size, color=theme.MUTED)


def primary_button(label: str, on_click, icon: Optional[str] = None, expand: bool = False) -> ft.ElevatedButton:
    return ft.ElevatedButton(
        content=ft.Text(label, weight=ft.FontWeight.BOLD),
        icon=icon,
        bgcolor=theme.PRIMARY,
        color="#FFFFFF",
        on_click=on_click,
        expand=expand,
        elevation=0,
    )


def wide_button(label: str, on_click, icon: Optional[str] = None) -> ft.Row:
    """Tombol utama yang beneran selebar induknya.

    Di dalam Column, `expand=True` ngatur tinggi -- bukan lebar. Jadi buat
    CTA full-width tombolnya dibungkus Row dulu.
    """
    return ft.Row([primary_button(label, on_click, icon=icon, expand=True)], spacing=0)


def soft_button(label: str, on_click, icon: Optional[str] = None) -> ft.OutlinedButton:
    return ft.OutlinedButton(
        content=ft.Text(label),
        icon=icon,
        on_click=on_click,
        style=ft.ButtonStyle(color=theme.ON_BACKGROUND),
    )


def med_icon(size: float = 18, color: str = "#FFFFFF") -> ft.Image:
    """Ilustrasi botol obat rounded, senada gaya Kalem -- ganti
    ft.Icons.MEDICATION yang gayanya beda (sudut tajam khas Material).

    SVG-nya cuma placeholder hitam; warna asli di-set di sini lewat
    color_blend_mode SRC_IN, jadi satu file bisa dipakai putih di banner
    berwarna maupun warna palet di latar polos.
    """
    return ft.Image(
        src="med_icon.svg",
        width=size,
        height=size,
        color=color,
        color_blend_mode=ft.BlendMode.SRC_IN,
    )


def banner(text: str, color: str, icon: Optional[str] = None) -> ft.Container:
    row_items: list[ft.Control] = []
    if icon == "med":
        row_items.append(med_icon(18, "#FFFFFF"))
    elif icon:
        row_items.append(ft.Icon(icon, color="#FFFFFF", size=18))
    row_items.append(ft.Text(text, color="#FFFFFF", size=12.5, expand=True))
    return ft.Container(
        content=ft.Row(row_items, spacing=10),
        bgcolor=color,
        border_radius=14,
        padding=ft.Padding.symmetric(vertical=10, horizontal=14),
    )


def section_header(text: str) -> ft.Text:
    return ft.Text(
        text.upper(),
        size=11,
        weight=ft.FontWeight.BOLD,
        color=theme.MUTED,
    )


def page_header(text: str, on_back=None, leading: Optional[ft.Control] = None) -> ft.Control:
    """Judul halaman, opsional dengan tombol kembali & ikon kecil di depan judul."""
    title_row: list[ft.Control] = []
    if leading:
        title_row.append(leading)
    title_row.append(title(text, 22 if on_back is None else 20))

    if on_back is None:
        return ft.Row(title_row, spacing=8) if leading else title(text, 22)
    return ft.Row(
        [
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                icon_color=theme.ON_BACKGROUND,
                on_click=on_back,
            ),
            *title_row,
        ],
        spacing=4,
    )


def empty_state(text: str, icon: str = ft.Icons.INBOX) -> ft.Container:
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(icon, size=34, color=theme.BORDER),
                ft.Text(text, size=12.5, color=theme.MUTED, text_align=ft.TextAlign.CENTER),
            ],
            spacing=8,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        alignment=ft.Alignment.CENTER,
        padding=24,
    )


def disclaimer(text: str) -> ft.Text:
    return ft.Text(text, size=10.5, color=theme.MUTED)


def choice_chip(label: str, active: bool, on_click) -> ft.Container:
    """Chip pilihan tunggal/ganda -- dipakai onboarding & edit profil di Settings."""
    return ft.Container(
        content=ft.Text(
            label,
            size=12.5,
            color="#FFFFFF" if active else theme.ON_BACKGROUND,
            text_align=ft.TextAlign.CENTER,
        ),
        bgcolor=theme.PRIMARY if active else theme.SURFACE,
        border=ft.Border.all(1, theme.PRIMARY if active else theme.BORDER),
        border_radius=12,
        padding=ft.Padding.symmetric(vertical=10, horizontal=14),
        on_click=on_click,
        ink=True,
    )


def nav_link_card(icon: str, icon_color: str, title_text: str, subtitle_text: str, on_click) -> ft.Container:
    """Kartu 'buka halaman lain' -- ikon + judul + subjudul + chevron."""
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(icon, color=icon_color),
                ft.Column(
                    [
                        ft.Text(title_text, weight=ft.FontWeight.BOLD, color=theme.ON_BACKGROUND),
                        ft.Text(subtitle_text, size=11.5, color=theme.MUTED),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.MUTED, size=20),
            ],
            spacing=12,
        ),
        bgcolor=theme.SURFACE,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=theme.CARD_RADIUS,
        padding=16,
        on_click=on_click,
        ink=True,
    )


def upgrade_hint(text: str, on_click=None) -> ft.Container:
    """Ajakan upgrade yang halus -- bukan popup yang ngalangin jalan.

    Nada & warnanya sengaja tenang (tertiary, bukan merah/kuning alarm):
    ini penawaran, bukan error. Fungsi inti app nggak pernah ke-lock,
    jadi kartu ini nggak boleh kerasa kayak tembok.
    """
    row: list[ft.Control] = [
        ft.Icon(ft.Icons.WORKSPACE_PREMIUM, color=theme.TERTIARY, size=18),
        ft.Text(text, size=11.5, color=theme.MUTED, expand=True),
    ]
    if on_click:
        row.append(ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.MUTED, size=16))
    return ft.Container(
        content=ft.Row(row, spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
        bgcolor=theme.BACKGROUND,
        border=ft.Border.all(1, theme.BORDER),
        border_radius=12,
        padding=ft.Padding.symmetric(vertical=10, horizontal=12),
        on_click=on_click,
        ink=bool(on_click),
    )


def premium_badge(size: float = 9) -> ft.Container:
    """Label PREMIUM kecil buat nempel di judul fitur berbayar.

    Dipasang di fitur premium yang KELIHATAN tapi belum kebuka -- jadi user
    tau apa yang dia dapet kalau upgrade, tanpa harus baca halaman harga.
    Sengaja kecil & tenang: ini penanda, bukan iklan yang ngalangin.
    """
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.WORKSPACE_PREMIUM, size=size + 2, color="#FFFFFF"),
                ft.Text("PREMIUM", size=size, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
            ],
            spacing=3,
            tight=True,
        ),
        bgcolor=theme.TERTIARY,
        border_radius=8,
        padding=ft.Padding.symmetric(vertical=2, horizontal=6),
    )


def premium_header(judul: str, terkunci: bool) -> ft.Control:
    """Judul section + badge PREMIUM kalau fiturnya belum kebuka."""
    baris: list[ft.Control] = [section_header(judul)]
    if terkunci:
        baris.append(premium_badge())
    return ft.Row(baris, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)


# Kalimat rayaan pas tugas kelar. Diacak biar nggak kerasa robot yang
# ngulang kalimat yang sama tiap kali.
REWARD_LINES = [
    "Satu kelar! 🎉",
    "Mantap, jalan terus 🌱",
    "Nice. Itu barusan progress ✨",
    "Kelar satu. Nggak harus semua kok 💚",
    "Yes! Kamu barusan mulai DAN selesai 🙌",
]


def reward_overlay(page: ft.Page, pesan: str = "") -> None:
    """Rayaan kecil pas tugas selesai -- muncul sebentar terus ilang sendiri.

    KENAPA INI ADA
    --------------
    Otak ADHD kurang sensitif ke reward yang jauh & abstrak ("nanti nilai
    kamu bagus"), tapi responsif ke umpan balik yang LANGSUNG. Nyentang
    tugas tanpa apa-apa yang terjadi itu momen kosong; satu detik rayaan
    bikin selesai kerasa selesai.

    Sengaja NGGAK pakai dialog: dialog butuh di-dismiss, dan itu malah
    nambah kerjaan. Ini muncul-sendiri, ilang-sendiri.
    """
    import asyncio
    import random

    teks = pesan or random.choice(REWARD_LINES)
    kartu = ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.CELEBRATION, color="#FFFFFF", size=20),
                ft.Text(teks, size=13.5, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
            ],
            spacing=8,
            tight=True,
        ),
        bgcolor=theme.SUCCESS,
        border_radius=16,
        padding=ft.Padding.symmetric(vertical=12, horizontal=18),
        # Mulai kecil & transparan, lalu mengembang -- gerakannya yang bikin
        # kerasa "muncul", bukan sekadar teks yang tiba-tiba ada.
        scale=0.7,
        opacity=0.0,
        animate_scale=ft.Animation(220, ft.AnimationCurve.EASE_OUT_BACK),
        animate_opacity=ft.Animation(220, ft.AnimationCurve.EASE_OUT),
    )
    lapisan = ft.Container(
        content=kartu,
        alignment=ft.Alignment.CENTER,
        expand=True,
    )

    async def main():
        page.overlay.append(lapisan)
        page.update()
        await asyncio.sleep(0.02)          # biar state awal sempat kerender
        kartu.scale, kartu.opacity = 1.0, 1.0
        page.update()
        await asyncio.sleep(1.1)
        kartu.opacity = 0.0
        page.update()
        await asyncio.sleep(0.25)
        if lapisan in page.overlay:
            page.overlay.remove(lapisan)
            page.update()

    page.run_task(main)


class ProgresAI:
    """Bar progres buat panggilan Gemini -- BERDASAR waktu asli, bukan hiasan.

    KENAPA BAR, BUKAN LINGKARAN MUTER
    ---------------------------------
    Spinner cuma bilang "lagi jalan", nggak bilang "sebentar lagi". Buat
    orang ADHD, nunggu tanpa tau berapa lama itu justru titik paling gampang
    ditinggal -- dan begitu ditinggal, hasilnya nggak pernah kelihatan.

    Panjangnya dihitung dari MEDIAN lama panggilan sebelumnya
    (`ai_client.perkiraan_lama()`), jadi angkanya beneran punya dasar.

    DUA ATURAN BIAR NGGAK BOHONG
    ----------------------------
    1. Nggak pernah nyentuh 100% sebelum jawabannya nyampe. Mentok 92% terus
       nunggu di situ. Bar yang penuh tapi layarnya diem itu lebih ngeselin
       daripada bar yang jujur bilang "masih nunggu".
    2. Kalau lewat dari perkiraan, teksnya ganti jadi "agak lama nih" --
       bukan diem-diem nambahin waktu terus.
    """

    # Batas atas sebelum jawaban nyampe. Sisanya buat lompatan terakhir.
    PLAFON = 0.92

    def __init__(self, label: str = "Kalem lagi nyusun..."):
        from app.core import ai_client

        self.perkiraan = ai_client.perkiraan_lama()
        self.terukur = ai_client.punya_ukuran()
        self.bar = ft.ProgressBar(
            value=0.0, color=theme.PRIMARY, bgcolor=theme.BORDER, bar_height=6
        )
        self.judul = ft.Text(label, size=12.5, color=theme.ON_BACKGROUND)
        self.detik = ft.Text("", size=10.5, color=theme.MUTED)
        self.selesai = False

    def kartu(self) -> ft.Control:
        return card(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.AUTO_AWESOME, size=16, color=theme.TERTIARY),
                            self.judul,
                        ],
                        spacing=8,
                    ),
                    self.bar,
                    self.detik,
                ],
                spacing=8,
            ),
            padding=14,
        )

    def tick(self, lewat: float) -> None:
        """Update tampilan. `lewat` = detik sejak panggilan dimulai."""
        if self.selesai:
            return
        rasio = min(lewat / max(self.perkiraan, 0.5), 1.0)
        self.bar.value = min(rasio * self.PLAFON, self.PLAFON)
        if lewat > self.perkiraan * 1.5:
            self.detik.value = "Agak lama nih — masih ditunggu."
        elif self.terukur:
            sisa = max(0, self.perkiraan - lewat)
            self.detik.value = (
                f"biasanya ~{self.perkiraan:.0f} detik · sisa ~{sisa:.0f} detik"
                if sisa >= 1
                else "hampir kelar..."
            )
        else:
            self.detik.value = "panggilan pertama — nyari tau biasanya berapa lama"

    def tuntas(self) -> None:
        self.selesai = True
        self.bar.value = 1.0
        self.detik.value = ""


async def jalankan_dengan_progres(page: ft.Page, holder: ft.Container, kerja, label: str):
    """Jalanin `kerja()` di thread lain sambil bar progresnya jalan.

    Panggilan Gemini itu blocking. Tanpa dilempar ke thread, seluruh UI beku
    dan bar progresnya nggak akan pernah gerak -- persis kebalikan dari yang
    mau dicapai.
    """
    import asyncio

    progres = ProgresAI(label)
    holder.content = progres.kartu()
    page.update()

    mulai = asyncio.get_event_loop().time()
    tugas = asyncio.get_event_loop().run_in_executor(None, kerja)
    while not tugas.done():
        progres.tick(asyncio.get_event_loop().time() - mulai)
        page.update()
        await asyncio.sleep(0.1)
    progres.tuntas()
    page.update()
    return await tugas


def show_reset_confirm(page: ft.Page, on_confirmed) -> None:
    """Dialog konfirmasi 'Hapus semua data' -- satu sumber, dipakai dev
    button di Home (di-gate DEMO_MODE) dan tombol resmi di Settings."""

    def do_reset(ev):
        page.pop_dialog()
        on_confirmed()

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text("Reset semua data?", size=16),
            content=ft.Text(
                "Profil, semua tugas, catatan mood, diary, riwayat SOS, dan setelan "
                "obat bakal dihapus. Nggak bisa dibalikin.",
                size=13,
            ),
            actions=[
                ft.TextButton(content=ft.Text("Batal"), on_click=lambda ev: page.pop_dialog()),
                ft.ElevatedButton(
                    content=ft.Text("Hapus semua", weight=ft.FontWeight.BOLD),
                    bgcolor=theme.DANGER,
                    color="#FFFFFF",
                    elevation=0,
                    on_click=do_reset,
                ),
            ],
        )
    )
