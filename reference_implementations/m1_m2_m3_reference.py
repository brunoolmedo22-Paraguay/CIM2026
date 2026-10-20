"""Referencias mínimas testeables de M1/M2/M3 para Claude, no son app.
M2 emplea Tcell [°C], M3 Huld emplea Tmodule posterior [°C].
Fuentes: PVWatts (pvlib) y PVGIS JRC (urls docs/FORMULACIONES.md).
"""
from __future__ import annotations
import numpy as np

HULD_K_CSI_CURRENT = (-0.017237, -0.040465, -0.004702,
                      0.000149, 0.000170, 0.000005)

def _g(g_poa):
    g=np.asarray(g_poa,dtype=float)
    if np.any(~np.isfinite(g)) or np.any(g<0):
        raise ValueError('Gpoa debe ser finita y >= 0 (limpiar antes el dataset)')
    return g

def m1_irradiance(g_poa, p_stc_W):
    return float(p_stc_W)*_g(g_poa)/1000.

def m2_pvwatts_dc(g_poa, temp_cell_C, p_stc_W, gamma_fraction_per_C):
    g=_g(g_poa)
    t=np.asarray(temp_cell_C,dtype=float)
    return np.maximum(0.,float(p_stc_W)*(g/1000.)*(1.+float(gamma_fraction_per_C)*(t-25.)))

def m3_huld(g_poa, temp_module_C, p_stc_W, k=HULD_K_CSI_CURRENT):
    g=_g(g_poa)
    t=np.asarray(temp_module_C,dtype=float)
    if len(k)!=6:raise ValueError('Huld necesita seis coeficientes')
    u=g/1000.
    lu=np.log(np.maximum(u,1e-12))
    dt=t-25.
    k1,k2,k3,k4,k5,k6=k
    eta=1+k1*lu+k2*lu**2+k3*dt+k4*dt*lu+k5*dt*lu**2+k6*dt**2
    return np.where(g>0,np.maximum(0.,float(p_stc_W)*u*eta),0.)
