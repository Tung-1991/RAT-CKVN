"""One ready-to-use VN30 protection policy; never arms or submits orders."""
from dataclasses import asdict


def shared_exit_settings(values):
    """Fixed execution choices for the single ready-to-use RULE."""
    return {**values, 'tp_enabled': False, 'tp_distance': 0.0,
            'arm_policy': 'AUTO', 'dynamic_policy': 'AUTO',
            'arm_basis': 'REMAINING', 'dynamic_basis': 'REMAINING',
            'arm_close_pct': 50.0, 'dynamic_close_pct': 50.0,
            'atr_start_enabled': True, 'atr_start_multiplier': .5,
            'atr_trail_enabled': True, 'atr_trail_multiplier': .8,
            'retention_enabled': True, 'retention_pct': 70.0,
            'retention_until_enabled': False, 'retention_until': 0.0,
            'arm_repeat_below_arm': True}


def default_exit_settings():
    from ckps.models import ExitSettings
    return asdict(ExitSettings(
        distance_unit='PRICE_PERCENT',
        sl_enabled=True, sl_distance=.5,
        tp_enabled=False, tp_distance=0,
        arm_enabled=True, arm_gain=1, trail_gap=.25,
        arm_policy='AUTO', arm_close_pct=50, arm_basis='REMAINING',
        arm_repeat=True, arm_repeat_below_arm=True, repeat_gap=.25,
        dynamic_enabled=True, dynamic_policy='AUTO', dynamic_close_pct=50,
        dynamic_basis='REMAINING', dynamic_repeat=True,
        atr_start_enabled=True, atr_start_multiplier=.5,
        atr_trail_enabled=True, atr_trail_multiplier=.8,
        retention_enabled=True, retention_pct=70,
        retention_until_enabled=False, retention_until=0,
    ).validate())
