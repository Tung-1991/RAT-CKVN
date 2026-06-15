# -*- coding: utf-8 -*-
import pandas as pd

def get_signal_vector(df: pd.DataFrame, params: dict, context: dict = None) -> int:
    p = params.get("period", 20)
    mult = params.get("multiplier", 1.1)
    
    if len(df) < p:
        return 0
        
    # Tính SMA Volume thủ công nhẹ nhàng vì DataEngine không tính
    vol_sma = df['volume'].rolling(window=p).mean().iloc[-1]
    curr_vol = df['volume'].iloc[-1]
    
    # Nếu Volume đột biến
    if curr_vol > (vol_sma * mult):
        close = df['close'].iloc[-1]
        open_p = df['open'].iloc[-1]
        
        # Nến xanh volume lớn
        if close > open_p: return 1
        # Nến đỏ volume lớn
        if close < open_p: return -1
        
    return 0