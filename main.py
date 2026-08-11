"""Entry point kompatibilitas untuk menjalankan aplikasi."""
import os

import flet as ft

from app.main import ASSETS_DIR, main


if __name__ == "__main__":
    port_text = os.getenv("PORT") or os.getenv("FLET_SERVER_PORT") or ""
    web_mode = os.getenv("FOCUSBUDDY_WEB", "").lower() in {"1", "true", "yes"}
    web_mode = web_mode or bool(port_text)
    ft.run(
        main,
        assets_dir=ASSETS_DIR,
        host="0.0.0.0" if web_mode else None,
        port=int(port_text) if port_text else 0,
        view=ft.AppView.WEB_BROWSER if web_mode else ft.AppView.FLET_APP,
    )
