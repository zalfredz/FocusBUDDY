"""Komponen perekam suara sementara untuk mengisi field teks yang bisa diedit."""
from __future__ import annotations

import asyncio
from collections.abc import Callable

import flet as ft
import flet_audio_recorder as far

from app import theme, ui_helpers
from app.core import speech_to_text


class VoiceDiary:

    def __init__(
        self,
        page: ft.Page,
        story_field: ft.TextField,
        on_busy: Callable[[bool], None],
        idle_label: str = "",
    ) -> None:
        self.page = page
        self.story_field = story_field
        self.on_busy = on_busy
        self.idle_label = idle_label
        self.active = True
        self.recording = False
        self.processing = False
        self.stopping = False
        self.inline = False
        self.seconds = 0
        self.token = 0
        self.chunks = bytearray()

        self.holder = ft.Container()
        self.status = ft.Text("", size=11.5, color=theme.MUTED)
        self.recorder = far.AudioRecorder(
            configuration=far.AudioRecorderConfiguration(
                encoder=far.AudioEncoder.PCM16BITS,
                sample_rate=speech_to_text.SAMPLE_RATE,
                channels=speech_to_text.CHANNELS,
                # Ambil sinyal mikrofon apa adanya. Efek ini tidak tersedia secara
                # konsisten di semua perangkat dan dapat mengecilkan suara yang
                # sebenarnya masih jelas untuk transkripsi.
                suppress_noise=False,
                cancel_echo=False,
                auto_gain=False,
            ),
            on_stream=self._on_audio_chunk,
        )
        self.render()

    def control(self) -> ft.Control:
        return ft.Column([self.holder, self.status], spacing=5)

    def embed_in_field(self) -> ft.Control:
        """Tempatkan tombol rekam ringkas di dalam field dan kembalikan statusnya."""
        self.inline = True
        self.story_field.suffix = self.holder
        self.render()
        return self.status

    def sync_with_text(self) -> None:
        """Sembunyikan tombol inline saat user sudah mulai mengetik."""
        self.render()
        self.page.update()

    def _on_audio_chunk(self, event: far.AudioRecorderStreamEvent) -> None:
        # Beberapa browser baru mengirim chunk terakhir ketika stop_recording()
        # sedang berjalan. Tetap terima chunk tersebut sampai proses stop benar-
        # benar selesai agar akhir (atau seluruh rekaman pendek) tidak terpotong.
        if not self.active or not (self.recording or self.stopping):
            return
        remaining = speech_to_text.MAX_PCM_BYTES - len(self.chunks)
        if remaining > 0:
            self.chunks.extend(event.chunk[:remaining])

    def render(self) -> None:
        self.on_busy(self.recording or self.processing)
        if self.inline:
            self.holder.content = self._inline_control()
        elif self.processing:
            self.holder.content = self._processing_card()
        elif self.recording:
            self.holder.content = self._recording_card()
        else:
            self.holder.content = self._idle_card()
        self.holder.visible = (
            not self.inline
            or self.recording
            or self.processing
            or not (self.story_field.value or "").strip()
        )

    def _inline_control(self) -> ft.Control:
        if self.processing:
            return ft.ProgressRing(
                width=22,
                height=22,
                stroke_width=3,
                color=theme.PRIMARY,
                tooltip="KALEM lagi mengubah suara jadi tulisan…",
            )
        if self.recording:
            left = speech_to_text.MAX_RECORD_SECONDS - self.seconds
            return ft.IconButton(
                icon=ft.Icons.STOP_CIRCLE_OUTLINED,
                icon_color=theme.DANGER,
                icon_size=22,
                tooltip=f"Selesai merekam · sisa {self._format_seconds(left)}",
                on_click=self.finish,
            )
        return ft.IconButton(
            icon=ft.Icons.MIC_NONE,
            icon_color=theme.PRIMARY,
            icon_size=21,
            tooltip="Isi pakai suara · maksimal 120 detik",
            on_click=self.start,
        )

    def _processing_card(self) -> ft.Control:
        return ft.Container(
            content=ft.Row(
                [
                    ft.ProgressRing(width=22, height=22, stroke_width=3),
                    ft.Column(
                        [
                            ft.Text(
                                "KALEM lagi mengubah suara jadi tulisan…",
                                size=12.5,
                                weight=ft.FontWeight.BOLD,
                                color=theme.ON_BACKGROUND,
                            ),
                            ft.Text(
                                "Rekamannya diproses sementara dan tidak disimpan sebagai audio.",
                                size=10.5,
                                color=theme.MUTED,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=12,
            ),
            bgcolor=theme.BACKGROUND,
            border=ft.Border.all(1, theme.PRIMARY),
            border_radius=12,
            padding=12,
        )

    def _recording_card(self) -> ft.Control:
        left = speech_to_text.MAX_RECORD_SECONDS - self.seconds
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.MIC, color=theme.DANGER, size=22),
                            ft.Column(
                                [
                                    ft.Text(
                                        "KALEM lagi mendengarkan…",
                                        size=12.5,
                                        weight=ft.FontWeight.BOLD,
                                        color=theme.ON_BACKGROUND,
                                    ),
                                    ft.Text(
                                        f"Sisa {self._format_seconds(left)} · cerita aja seperti biasa",
                                        size=10.5,
                                        color=theme.MUTED,
                                    ),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Row(
                        [
                            ft.TextButton(
                                content=ft.Text("Batal", color=theme.MUTED),
                                on_click=self.cancel,
                            ),
                            ft.Container(expand=True),
                            ui_helpers.primary_button(
                                "Selesai", self.finish, icon=ft.Icons.STOP
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=8,
            ),
            bgcolor=theme.BACKGROUND,
            border=ft.Border.all(1, theme.DANGER),
            border_radius=12,
            padding=12,
        )

    def _idle_card(self) -> ft.Control:
        if self.idle_label:
            return ft.OutlinedButton(
                content=ft.Text(
                    self.idle_label,
                    color=theme.ON_BACKGROUND,
                    weight=ft.FontWeight.W_600,
                ),
                icon=ft.Icons.MIC_NONE,
                tooltip="Isi pakai suara · maksimal 120 detik",
                style=ft.ButtonStyle(
                    color=theme.PRIMARY,
                    side=ft.BorderSide(1, theme.BORDER),
                    shape=ft.RoundedRectangleBorder(radius=12),
                ),
                on_click=self.start,
            )
        return ft.Row(
            [
                ft.IconButton(
                    icon=ft.Icons.MIC_NONE,
                    icon_color=theme.PRIMARY,
                    icon_size=21,
                    tooltip="Isi pakai suara · maksimal 120 detik",
                    on_click=self.start,
                )
            ],
            alignment=ft.MainAxisAlignment.END,
            spacing=0,
        )

    @staticmethod
    def _format_seconds(seconds: int) -> str:
        minutes, remainder = divmod(max(0, seconds), 60)
        return f"{minutes:02d}:{remainder:02d}"

    async def _countdown(self, token: int) -> None:
        while (
            self.active
            and self.recording
            and self.token == token
            and self.seconds < speech_to_text.MAX_RECORD_SECONDS
        ):
            await asyncio.sleep(1)
            if not self.recording or self.token != token:
                return
            self.seconds += 1
            self.render()
            self.page.update()
        if self.recording and self.token == token:
            await self.finish(None)

    async def start(self, e) -> None:
        if self.recording or self.processing:
            return
        self._set_status("Meminta izin mikrofon…")
        self.page.update()
        try:
            allowed = await self.recorder.has_permission()
        except Exception:
            allowed = False
        if not allowed:
            self._set_status(
                "Izin mikrofon belum diberikan. Izinkan mikrofon di browser, "
                "atau tetap isi secara manual.",
                theme.WARN,
            )
            self.page.update()
            return

        self.chunks.clear()
        self.seconds = 0
        self.token += 1
        token = self.token
        self.recording = True
        try:
            started = await self.recorder.start_recording()
        except Exception:
            started = False
        if not started:
            self.recording = False
            self._set_status(
                "Mikrofon belum bisa dimulai. Coba lagi atau isi manual.",
                theme.WARN,
            )
            self.render()
            self.page.update()
            return

        self._set_status("")
        self.render()
        self.page.update()
        self.page.run_task(self._countdown, token)

    async def cancel(self, e) -> None:
        if self.stopping:
            return
        self.stopping = True
        self.recording = False
        self.token += 1
        try:
            await self.recorder.cancel_recording()
        except Exception:
            pass
        self.chunks.clear()
        self.seconds = 0
        self.stopping = False
        self._set_status("Rekaman dibatalkan dan tidak disimpan.")
        self.render()
        if self.active:
            self.page.update()

    async def finish(self, e) -> None:
        if not self.recording or self.stopping:
            return
        self.stopping = True
        self.recording = False
        self.token += 1
        try:
            await self.recorder.stop_recording()
        except Exception:
            self.stopping = False
            self.chunks.clear()
            self._set_status(
                "Rekaman belum bisa diproses. Coba lagi atau ketik manual.",
                theme.WARN,
            )
            self.render()
            if self.active:
                self.page.update()
            return

        # Beri event stream yang sudah berada dalam antrean satu kesempatan untuk
        # sampai ke Python sebelum buffer dibekukan untuk transkripsi.
        await asyncio.sleep(0.05)

        pcm = bytes(self.chunks)
        self.chunks.clear()
        self.stopping = False
        self.processing = True
        self._set_status("")
        self.render()
        if self.active:
            self.page.update()

        transcript, error = await asyncio.to_thread(
            speech_to_text.transcribe_pcm16, pcm
        )
        del pcm
        self.processing = False
        if not self.active:
            return

        if transcript:
            existing = (self.story_field.value or "").strip()
            self.story_field.value = (
                f"{existing}\n\n{transcript}" if existing else transcript
            )
            self.story_field.error = None
            self._set_status(
                "Udah jadi tulisan. Baca dan edit dulu sebelum disimpan.",
                theme.PRIMARY,
            )
        else:
            self._set_status(error or speech_to_text.PESAN_GAGAL, theme.WARN)
        self.render()
        self.page.update()

    def cleanup(self) -> None:
        self.active = False
        self.token += 1
        self.processing = False
        if self.recording or self.stopping:
            self.recording = False
            self.page.run_task(self.recorder.cancel_recording)
        self.chunks.clear()

    def _set_status(self, text: str, color: str = theme.MUTED) -> None:
        self.status.value = text
        self.status.color = color
