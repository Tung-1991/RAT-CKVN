from __future__ import annotations

import argparse
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk


def main():
    parser = argparse.ArgumentParser(description="RAT VN30 · Phái sinh · Vào lệnh tay và quản lý E/M")
    parser.parse_args()
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("dark-blue")
    from ckps.dashboard.window import App
    try:
        app=App()
        app.mainloop()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("RAT VN30 chưa khởi động được", str(exc), parent=root)
        root.destroy()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
