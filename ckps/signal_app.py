"""Backend application entry point; deliberately separate from trading."""
def main():
    import customtkinter as ctk
    ctk.set_appearance_mode('Dark')
    ctk.set_default_color_theme('dark-blue')
    from ckps.dashboard.signal_app import SignalApp
    app=SignalApp()
    app.mainloop()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
