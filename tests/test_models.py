import warnings

import numpy as np
import pytest

from cim26.constants import HULD_COEFFICIENT_SETS
from cim26.data.catalog import catalog_modules
from cim26.pvcore import models as M
from cim26.pvcore.module import ModuleSpec
from cim26.pvcore.thermal import Conditions

K = HULD_COEFFICIENT_SETS["PVGIS_cSi_current"]["k"]


def cond(g, tm, tc):
    return Conditions(g_poa_Wm2=np.atleast_1d(g), t_module_C=np.atleast_1d(tm), t_cell_C=np.atleast_1d(tc))


@pytest.mark.parametrize("mid", ["M1", "M2", "M3"])
def test_stc_gives_pstc(mid, supsi_module):
    p = M.prepare(mid, supsi_module)
    out = M.predict(mid, cond(1000.0, 25.0, 25.0), p)
    assert out.p_mpp_W[0] == pytest.approx(supsi_module.p_stc_W, rel=1e-12)


@pytest.mark.parametrize("mid", ["M1", "M2", "M3", "M4"])
def test_zero_irradiance_no_log_warning(mid, supsi_module, supsi_cal):
    p = M.prepare(mid, supsi_module, supsi_cal[0])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with np.errstate(all="raise"):
            out = M.predict(mid, cond(0.0, 30.0, 30.0), p)
    assert out.p_mpp_W[0] == 0.0
    assert out.status[0] == 1


def test_m2_hand_calculation_and_decreasing(supsi_module):
    p = M.prepare("M2", supsi_module)
    hand = 285.68591743441357 * 0.8 * (1 + (-0.405 / 100) * (45 - 25))
    assert M.m2_power(800, 45, p.p_stc_W, p.gamma_per_C) == pytest.approx(hand, rel=1e-14)
    t = np.array([25, 40, 60, 75.0])
    assert np.all(np.diff(M.m2_power(np.full(4, 1000.0), t, p.p_stc_W, p.gamma_per_C)) < 0)


def test_huld_hand_and_reference_impl(supsi_module):
    import sys
    from tests.conftest import ROOT
    sys.path.insert(0, str(ROOT / "reference_implementations"))
    from m1_m2_m3_reference import HULD_K_CSI_CURRENT, m3_huld
    assert tuple(HULD_K_CSI_CURRENT) == tuple(K)
    G, T = 500.0, 40.0
    u, lu, dT = 0.5, np.log(0.5), 15.0
    eta = 1 + K[0]*lu + K[1]*lu**2 + K[2]*dT + K[3]*dT*lu + K[4]*dT*lu**2 + K[5]*dT**2
    assert M.m3_power(G, T, 285.6859, K) == pytest.approx(285.6859 * u * eta, rel=1e-14)
    g = np.array([0, 50, 200, 700, 1100.0]); t = np.array([10, 20, 35, 50, 70.0])
    np.testing.assert_allclose(M.m3_power(g, t, 285.6859, K), m3_huld(g, t, 285.6859), rtol=1e-13)


def test_huld_unavailable_for_cdte():
    m = ModuleSpec(id="x", kind="usuario", technology="CdTe", p_stc_W=100.0)
    assert not M.availability("M3", m).available


def test_missing_gamma_marks_m2_unavailable():
    m = ModuleSpec(id="x", kind="usuario", technology="Mono-Si", p_stc_W=100.0)
    av = M.availability("M2", m)
    assert not av.available and "γ" in av.reason
    assert not M.availability("M4", m, None).available


def test_scalar_mode_equals_vector(supsi_module, supsi_cal):
    rng = np.random.default_rng(1)
    g = rng.uniform(100, 1100, 40); tm = rng.uniform(5, 60, 40)
    c = cond(g, tm, tm + g / 1000 * 3)
    for mid in M.MODEL_IDS:
        p = M.prepare(mid, supsi_module, supsi_cal[0])
        a = M.predict(mid, c, p, mode="vetorizado").p_mpp_W
        b = M.predict(mid, c, p, mode="escalar").p_mpp_W
        np.testing.assert_array_equal(a, b)


def test_array_scaling():
    np.testing.assert_allclose(M.scale_to_array(np.array([100.0, 0.0]), 3, 2), [600.0, 0.0])
    with pytest.raises(ValueError):
        M.scale_to_array(np.array([1.0]), 0, 1)


def test_canadian_catalog_all_models_with_classical_sdm():
    from cim26.calibration.classical import calibrate_classical
    m = catalog_modules()["CS6K-275P"]
    ref, rep = calibrate_classical(m)
    assert rep.success
    for mid in M.MODEL_IDS:
        assert M.availability(mid, m, ref).available
    out = M.predict("M4", cond(1000.0, 25.0, 25.0), M.prepare("M4", m, ref))
    assert out.p_mpp_W[0] == pytest.approx(m.v_mp_V * m.i_mp_A, rel=5e-4)
