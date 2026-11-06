"""Select a saved strategy preset; never starts a trading or signal runtime."""
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from ckps.config import ROOT
from ckps.services.presets import load_preset


def main():
    root=tk.Tk();root.withdraw()
    try:
        filename=filedialog.askopenfilename(parent=root,title='Nạp preset RULE',
            initialdir=str(ROOT/'support'/'presets'),filetypes=[('Preset JSON','*.json')])
        if not filename:return 0
        name,backup=load_preset(Path(filename))
        messagebox.showinfo('Đã nạp preset',f'{name}\nĐã nạp RULE. Mở lại app để sử dụng.\nBản sao cấu hình cũ: {backup}',parent=root)
        return 0
    except Exception as exc:
        messagebox.showerror('Chưa nạp được preset',str(exc),parent=root)
        return 1
    finally:root.destroy()


if __name__=='__main__':
    raise SystemExit(main())
