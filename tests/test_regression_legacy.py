"""O código portado reproduz o legado (equações não alteradas)."""
import numpy as np
import pandas as pd
import pytest

from cim26.calibration.classical import calibrate_classical
from cim26.data.catalog import catalog_modules
from cim26.data import weather as W
from cim26.pvcore import sdm as S
from cim26.pvcore.models import m1_power, m2_power
from cim26.pvcore.thermal import t_cell_noct
from cim26.simulate import simulate
from tests.legacy_import import legacy

CAT = catalog_modules()


def test_classical_calibration_identical_for_whole_catalog():
    with legacy() as L:
        for k, m in CAT.items():
            ref, rep = calibrate_classical(m)
            lp, lr = L.solver.extract_sdm_params(L.db.get_module(k).stc)
            assert rep.success == lr.success
            np.testing.assert_allclose([ref.IL_ref, ref.I0_ref, ref.Rs, ref.Rsh_ref, ref.n],
                                       [lp.IL_ref, lp.I0_ref, lp.Rs, lp.Rsh_ref, lp.n], rtol=1e-10)
            assert ref.a_ref == pytest.approx(lp.a_ref, rel=1e-14)


@pytest.mark.parametrize("key", ["CS6P-250P", "CS3W-450MS", "CS7L-600MS"])
def test_translate_and_mpp_identical(key):
    m = CAT[key]
    ref, _ = calibrate_classical(m)
    rng = np.random.default_rng(3)
    with legacy() as L:
        mod = L.db.get_module(key)
        lp, _ = L.solver.extract_sdm_params(mod.stc)
        for g, t in zip(rng.uniform(20, 1200, 25), rng.uniform(-5, 75, 25)):
            a = S.find_mpp(S.translate(ref, g, t))
            b = L.mpp.find_mpp(L.solver.translate_params(lp, mod.stc, g, t))
            for k in ("Pmp", "Vmp", "Voc", "Isc"):
                assert a[k] == pytest.approx(b[k], rel=1e-9, abs=1e-12)


def test_solvers_agree():
    ref, _ = calibrate_classical(CAT["CS6K-275P"])
    op = S.translate(ref, 650.0, 41.0)
    V = np.linspace(0, S.open_circuit_voltage(op), 25)
    a = S.current_from_voltage(V, op, "lambertw")
    np.testing.assert_allclose(a, S.current_from_voltage(V, op, "brentq"), atol=1e-8)
    np.testing.assert_allclose(a, S.current_from_voltage(V, op, "newton"), atol=1e-8)


def test_legacy_multimodel_equivalence():
    """M1 = modelo de irradiância do legado; M2 (PVWatts) = NOCT+eficiência do legado com a mesma Tcell;
    M4 = SDM do legado (simulate_timeseries) com a mesma Tcell NOCT."""
    key = "CS6U-330P"
    m = CAT[key]
    ref, _ = calibrate_classical(m)
    w = W.synthetic("Dia nublado", "Verão", duration_min=180, start="2025-01-01 10:00", step_min=1)
    prof = pd.DataFrame({"G": w.g_poa_Wm2, "Tamb": w.t_amb_C}, index=w.timestamp)
    with legacy() as L:
        mod = L.db.get_module(key)
        mod.sdm, _ = L.solver.extract_sdm_params(mod.stc)
        r1 = L.mm.simulate_irradiance_model(mod, prof, n_series=1, n_parallel=1)
        r2 = L.mm.simulate_noct_efficiency_model(mod, prof, n_series=1, n_parallel=1)
        r4 = L.mm.simulate_sdm_model(mod, prof, n_series=2, n_parallel=3)
    np.testing.assert_allclose(m1_power(w.g_poa_Wm2, m.p_stc_W), r1["P_module"], rtol=1e-12)
    tc = t_cell_noct(w.t_amb_C, w.g_poa_Wm2, m.noct_C)
    np.testing.assert_allclose(m2_power(w.g_poa_Wm2, tc, m.p_stc_W, m.gamma_per_C), r2["P_module"],
                               rtol=1e-9, atol=1e-9)
    res = simulate(m, w, ["M4"], ref, strategy="noct", n_series=2, n_parallel=3)
    np.testing.assert_allclose(res.table["P_M4_arranjo_W"], r4["P_array"], rtol=1e-9, atol=1e-9)
