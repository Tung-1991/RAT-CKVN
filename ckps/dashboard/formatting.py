from datetime import datetime

def money(value):
    return "—" if value is None else f"{value:,.0f} đ"

def price(value):
    return "—" if not value else f"{value:,.1f}"

def clock(stamp):
    return datetime.fromtimestamp(stamp).strftime("%d/%m %H:%M:%S") if stamp else "—"
