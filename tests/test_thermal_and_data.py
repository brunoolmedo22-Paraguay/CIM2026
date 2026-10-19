import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from cim26.data import supsi_field as F
from cim26.data import weather as W
from cim26.data.catalog import catalog_modules
from cim26.data.supsi_lab import SUPSI_LAB_LONG_CSV, check_lab, load_supsi_module_json, write_long_csv
from cim26.paths import PROJECT_ROOT
from cim26.pvcore import thermal as TH


def test_faiman_reproduces_nmot(supsi_module):
    t = TH.t_module_faiman(20.0, 800.0, 1.0, supsi_module.u0_W_m2K, supsi_module.u1_W_s_m3K)
    assert t == pytest.approx(supsi_module.extra["nmot_C"], abs=0.005)


def test_eq23_and_inverse():
    tc = TH.t_cell_from_t_module(40.0, 800.0, 3.0)
    assert tc == pytest.approx(42.4)
    assert TH.t_module_from_t_cell(tc, 800.0, 3.0) == pytest.approx(40.0)
    assert TH.t_cell_noct(20.0, 800.0, 45.0) == pytest.approx(45.0)


def test_raw_inputs_unchanged():
    man = json.loads((PROJECT_ROOT / "docs" / "MANIFIESTO_SHA256.json").read_text(encoding="utf-8"))["files"]
    for rel, info in man.items():
        if rel.startswith("input/SUPSI/"):
            h = hashlib.sha256((PROJECT_ROOT / rel).read_bytes()).hexdigest()
            assert h == info["sha256"], rel


def test_six_csv_timestamps_and_poa_vs_ghi(field):
    df, hashes = field
    assert len(hashes) == 6 and len(df) == 18705
    assert df["timestamp"].notna().all()
    assert df["timestamp"].iloc[0] == pd.Timestamp("2019-01-01 08:40:00")
    assert "g_poa_Wm2" in df and "ghi_Wm2" in df
    both = df[["g_poa_Wm2", "ghi_Wm2"]].dropna()
    assert not np.allclose(both["g_poa_Wm2"], both["ghi_Wm2"])     # séries distintas, não renomeadas


def test_quality_keeps_all_rows_and_common_pairs(field, supsi_module):
    df, _ = field
    q = F.assess_quality(df, F.QualityConfig(voc_stc_V=supsi_module.v_oc_V, p_stc_W=supsi_module.p_stc_W))
    assert len(q) == len(df)
    assert (~q["eligible"] == (q["reasons"] != "")).all()
    assert q.loc[q["eligible"], "g_poa_Wm2"].min() >= 100
    pairs = F.valid_pair_mask(q["timestamp"], q["eligible"].to_numpy())
    t = q["timestamp"]
    dt = (t.diff().dt.total_seconds() / 60).to_numpy()[1:]
    assert np.all(dt[pairs] <= 7.5)
    assert np.all(t.dt.date.to_numpy()[1:][pairs] == t.dt.date.to_numpy()[:-1][pairs])


def test_lab_matrix_and_sentinel(lab, tmp_path):
    checks = check_lab(lab, load_supsi_module_json())
    assert all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]
    assert not (lab.long.measured_value == 32).any()
    out = write_long_csv(lab, tmp_path / "regen.csv")
    assert out.read_bytes() == SUPSI_LAB_LONG_CSV.read_bytes()
    with pytest.raises(PermissionError):
        write_long_csv(lab, SUPSI_LAB_LONG_CSV)


def test_supsi_sheet_has_no_invented_fields(supsi_module):
    for f in ("v_mp_V", "i_mp_A", "n_cells_series", "manufacturer", "model"):
        assert getattr(supsi_module, f) is None


def test_catalog_equals_legacy():
    from tests.legacy_import import legacy
    ours = catalog_modules()
    with legacy() as L:
        assert set(ours) == set(L.db.MODULE_DB)
        for k, m in ours.items():
            s = L.db.get_module(k).stc
            assert (m.p_stc_W, m.v_oc_V, m.i_sc_A, m.v_mp_V, m.i_mp_A, m.n_cells_series) == \
                   (s.p_nom, s.v_oc, s.i_sc, s.v_mp, s.i_mp, s.n_cells)
            assert (m.alpha_isc_pct_C, m.beta_voc_pct_C, m.gamma_pmax_pct_C, m.noct_C) == \
                   (s.alpha_isc_pct, s.beta_voc_pct, s.gamma_pmax_pct, s.noct)


def test_ghi_is_never_renamed_poa():
    df = pd.DataFrame({"t": ["2025-01-01 10:00", "2025-01-01 10:05"], "ghi": [500, 520]})
    with pytest.raises(ValueError, match="GHI não é POA"):
        W.from_dataframe(df, "t", "ghi", "GHI")
    w = W.from_dataframe(df, "t", "ghi", "GHI", horizontal=True)
    assert any("horizontal" in n for n in w.notes)
