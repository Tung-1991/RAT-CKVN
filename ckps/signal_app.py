"""Signal-rule Blackbox panel, with a separate private pipe for analysis."""
def main():
    import sys
    if '--headless' in sys.argv:
        from ckps.services.signal_process import serve
        return serve(sys.stdin, sys.stdout)
    import customtkinter as ctk
    from ckps.dashboard.signal_app import SignalApp
    ctk.set_appearance_mode('Dark')
    ctk.set_default_color_theme('dark-blue')
    try:
        app=SignalApp()
        app.mainloop()
    except Exception as exc:
        import tkinter as tk
        from tkinter import messagebox
        root=tk.Tk();root.withdraw()
        messagebox.showerror('Blackbox chưa mở được',str(exc),parent=root)
        root.destroy()
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
