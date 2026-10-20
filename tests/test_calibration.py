import pytest

from cim26.calibration.classical import calibrate_classical


def test_multipoint_without_ns_vmp_imp(supsi_module, supsi_cal):
    ref, rep = supsi_cal
    assert supsi_module.n_cells_series is None and supsi_module.v_mp_V is None
    assert ref.n is None and ref.n_cells is None and ref.method == "multiponto_SUPSI_lab"
    assert rep.success and len(rep.residuals) == 66
    assert set(rep.lab_metrics["variable"]) == {"Pmp", "Isc", "Voc"}
    assert any("a_ref" in a for a in rep.assumptions)
    assert any("campo 2019 não usados" in a for a in rep.assumptions)
    assert rep.condition_number < 1e6 and len(rep.jacobian_singular_values) == 5
    assert rep.lab_metrics.set_index("variable").loc["Pmp", "RMSE"] < 5.0


def test_classical_refuses_incomplete_datasheet(supsi_module):
    with pytest.raises(ValueError, match="Vmp"):
        calibrate_classical(supsi_module)
