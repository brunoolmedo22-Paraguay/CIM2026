"""Medição de memória residente (RSS) do processo isolado do benchmark.

Linux: o pico (VmHWM) é reiniciado antes de cada chamada escrevendo "5" em
/proc/self/clear_refs → pico RSS real da chamada, sem thread de amostragem.
Outros SO: apenas RSS antes/depois via psutil (o pico intra-chamada NÃO é
observado; registrado como método diferente e declarado como limitação).
RSS ≠ tracemalloc (este mede apenas alocações Python, em passe separado).
"""

from __future__ import annotations

import os
import re

MiB = 1024.0 * 1024.0


class RSSMeter:
    def __init__(self):
        self.method = "rss_antes_depois_psutil"
        self._proc = None
        if os.path.exists("/proc/self/status") and os.path.exists("/proc/self/clear_refs"):
            try:
                with open("/proc/self/clear_refs", "w") as f:
                    f.write("5")
                self.method = "linux_vmhwm_reset"
            except OSError:
                pass
        if self.method != "linux_vmhwm_reset":
            try:
                import psutil
                self._proc = psutil.Process()
            except Exception:
                self.method = "nao_medido"

    def _status(self) -> dict:
        s = open("/proc/self/status").read()
        return {k: int(re.search(rf"{k}:\s+(\d+)", s).group(1)) * 1024 / MiB for k in ("VmRSS", "VmHWM")}

    def reset_peak(self) -> None:
        if self.method == "linux_vmhwm_reset":
            with open("/proc/self/clear_refs", "w") as f:
                f.write("5")

    def rss_MiB(self) -> float:
        if self.method == "linux_vmhwm_reset":
            return self._status()["VmRSS"]
        if self._proc is not None:
            return self._proc.memory_info().rss / MiB
        return float("nan")

    def peak_MiB(self, rss_before: float, rss_after: float) -> float:
        if self.method == "linux_vmhwm_reset":
            return self._status()["VmHWM"]
        if self._proc is not None:
            return max(rss_before, rss_after)
        return float("nan")
