"""Backend application entry point; deliberately separate from trading."""
def main():
    import sys
    if '--headless' in sys.argv:
        from ckps.services.signal_process import serve
        return serve(sys.stdin, sys.stdout)
    from ckps.services.signal_process import standalone
    return standalone()


if __name__=='__main__':
    raise SystemExit(main())
