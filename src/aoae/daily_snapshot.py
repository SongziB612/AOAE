"""Fail-closed validation of unadjusted daily capture, not data admission."""
import numpy as np
import pandas as pd


def validate_daily_frame(frame, start, end):
    frame = frame.copy()
    frame['date'] = pd.to_datetime(frame['date'], errors='raise')
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if frame.empty or frame['date'].isna().any():
        raise ValueError('empty snapshot or invalid date')
    if frame['date'].duplicated().any() or not frame['date'].is_monotonic_increasing:
        raise ValueError('duplicate or unordered dates')
    if (frame['date'] != frame['date'].dt.normalize()).any():
        raise ValueError('daily dates contain intraday timestamps')
    if start not in set(frame['date']) or not frame['date'].between(start, end).all():
        raise ValueError('missing overlap or out-of-range date')
    columns = ['open', 'high', 'low', 'close', 'volume', 'amount']
    for column in columns:
        frame[column] = pd.to_numeric(frame[column], errors='raise')
    if not np.isfinite(frame[columns].to_numpy(dtype=float)).all():
        raise ValueError('nonfinite daily values')
    if (frame[['open', 'high', 'low', 'close']] <= 0).any().any():
        raise ValueError('nonpositive price')
    if (frame[['volume', 'amount']] < 0).any().any():
        raise ValueError('negative volume or amount')
    if ((frame['low'] > frame[['open', 'close']].min(axis=1)) |
            (frame['high'] < frame[['open', 'close']].max(axis=1)) |
            (frame['low'] > frame['high'])).any():
        raise ValueError('inconsistent OHLC range')
    return frame
