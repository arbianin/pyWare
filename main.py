"""pyWare — Roblox external ESP. Run as ADMIN:  py main.py"""
import ctypes
import sys
import traceback


def need(what):
    print(f"[!] missing dependency: {what}. Run setup.bat first.", flush=True)
    sys.exit(1)


try:
    from PyQt5.QtWidgets import QApplication
except ImportError:
    need("PyQt5")

from pyware import config, engine
from pyware.overlay import Overlay


def main():
    try:
        admin = ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        admin = False
    if not admin:
        print("[!] not running as admin — memory reads will fail. Right-click -> Run as administrator.", flush=True)

    print("pyWare | overlay-only build (menu lives INSIDE Roblox, INSERT toggles it)", flush=True)
    print("Safe mode is OFF: everything is live. Flip it on in SYS for read-only ESP+aim.", flush=True)
    print(flush=True)

    try:
        config.load()
        print("config loaded", flush=True)
    except Exception:
        pass

    engine.attach()
    engine.start()

    app = QApplication([])
    ov = Overlay()
    ov.set_menu_open(True)
    ov.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("crashed — press ENTER to close...")
