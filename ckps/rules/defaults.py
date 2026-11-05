"""One ready-to-use VN30 protection policy; never arms or submits orders."""
from dataclasses import asdict


def shared_exit_settings(values):
    """Fixed execution permissions; preserve user protection thresholds."""
    return {**values,
            'arm_policy': 'AUTO', 'dynamic_policy': 'AUTO',
            'arm_basis': 'REMAINING', 'dynamic_basis': 'REMAINING',
            'arm_close_pct': 100.0, 'dynamic_close_pct': 100.0,
            'ema_exit_mode': 'REALTIME', 'ema_exit_interval': 'TICK'}


def default_exit_settings():
    from ckps.models import ExitSettings
    return asdict(ExitSettings(
        distance_unit='PRICE_PERCENT',
        trailing_unit='PRICE_PERCENT',
        sl_enabled=True, sl_distance=1,
        tp_enabled=False, tp_distance=0,
        ema_exit_enabled=True, ema_exit_fast=3, ema_exit_slow=6,
        arm_enabled=True, arm_gain=1, trail_gap=.3,
        arm_policy='AUTO', arm_close_pct=100, arm_basis='REMAINING',
        arm_repeat=False, arm_repeat_below_arm=False, repeat_gap=.3,
        dynamic_enabled=True, dynamic_policy='AUTO', dynamic_close_pct=100,
        dynamic_basis='REMAINING', dynamic_repeat=False,
        atr_start_enabled=True, atr_start_multiplier=.5,
        atr_trail_enabled=True, atr_trail_multiplier=.8,
        retention_enabled=True, retention_pct=65,
        retention_until_enabled=False, retention_until=0,
    ).validate())
