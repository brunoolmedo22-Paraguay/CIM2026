from __future__ import annotations

import numpy as np


def trapezoid_integral(y: np.ndarray, x: np.ndarray) -> float:
    """Integrate y(x) with a NumPy-version-safe trapezoidal rule.

    NumPy >= 2.0 provides ``np.trapezoid``. Older releases provide ``np.trapz``.
    NumPy 2.5+ removed ``np.trapz``; therefore the legacy function must be looked
    up lazily rather than being evaluated as a default argument to ``getattr``.
    """
    y_arr = np.asarray(y, dtype=float)
    x_arr = np.asarray(x, dtype=float)
    if len(y_arr) < 2:
        return 0.0
    if len(y_arr) != len(x_arr):
        raise ValueError("y e x devem possuir o mesmo número de pontos.")

    integrator = getattr(np, "trapezoid", None)
    if integrator is None:
        integrator = getattr(np, "trapz", None)
    if integrator is not None:
        return float(integrator(y_arr, x=x_arr))

    # Last-resort implementation if neither NumPy API is present.
    return float(np.sum((y_arr[:-1] + y_arr[1:]) * 0.5 * np.diff(x_arr)))
