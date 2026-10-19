import json

import numpy as np
import pandas as pd
import pytest

from cim26.data.anomalies import AnomalyConfig, detect_anomalies
from cim26.report.narrative import classify


def _df(rows):
    d = pd.DataFrame(rows, columns=["g_poa_Wm2", "p_mpp_measured_W", "isc_measured_A", "voc_measured_V", "t_module_C", "t_amb_C"])
    d["timestamp"] = pd.date_range("2019-05-01 10:00", periods=len(d), freq="5min")
    d["row_id"] = np.arange(len(d))
    return d


def test_physical_anomaly_rules():
    d = _df([[5, 50, 0.05, 38, 20, 15],        # A01 potência sem irradiância
             [800, 1, 7.6, 38, 45, 20],         # A02 irradiância sem potência (e A04)
             [500, 250, 4.7, 38, 35, 20],       # A03 P acima do plausível (PR 1,75)
             [800, 225, 7.6, 37, 45, 20],       # normal
             [800, 225, 4.0, 37, 45, 20]])      # A05 Isc incoerente
    a = detect_anomalies(d, 285.686, 9.4868, 39.71, AnomalyConfig())
    assert "A01" in a.anom_codes[0] and a.anom_severidade[0] == "erro"
    assert "A02" in a.anom_codes[1]
    assert "A03" in a.anom_codes[2]
    assert not any(c.startswith("A") for c in a.anom_codes[3].split(";") if c)      # só T01 (condição) pelos vizinhos
    assert a.anom_severidade[3] in ("", "condicao")
    assert "A05" in a.anom_codes[4] and a.anom_severidade[4] == "suspeito"


def test_supsi_dataset_anomaly_counts(field):
    df, _ = field
    a = detect_anomalies(df, 285.68591743441357, 9.486848514934435, 39.714731230689345)
    codes = a.anom_codes.fillna("")
    assert codes.str.contains("A01").sum() == 0          # nenhuma potência com irradiância nula no SUPSI 2019
    assert codes.str.contains("A02").sum() == 0
    assert codes.str.contains("A03").sum() > 0
    assert len(a) == len(df)


@pytest.mark.parametrize("args,cls", [((-0.6, -0.8, -0.4), "robusta"), ((-0.02, -0.04, -0.01), "indicativa"),
                                      ((0.1, -0.2, 0.3), "inconclusiva")])
def test_evidence_classification(args, cls):
    assert classify(*args)[0] == cls


def test_narrative_from_run_files(small_run):
    items = json.loads((small_run / "narrative.json").read_text(encoding="utf-8"))
    assert items[0]["secao"] == "sintese"
    assert not any(i["secao"] == "aviso" for i in items), [i for i in items if i["secao"] == "aviso"]
    me = pd.read_csv(small_run / "metrics_energy.csv")
    best = me.loc[me.NRMSE_media_pct.idxmin(), "modelo"]
    assert items[0]["texto"].startswith(best)
    secs = {i["secao"] for i in items}
    assert {"energia", "qualidade", "computacional", "integrada", "estatistica"} <= secs
    assert all(i["evidencia"] in ("robusta", "indicativa", "inconclusiva", "contexto") for i in items)
    pred = pd.read_csv(small_run / "predictions.csv")
    assert {"anom_codes", "anom_severidade", "isc_ratio", "transitorio"} <= set(pred.columns)
    qs = pd.read_csv(small_run / "quality_sensitivity.csv")
    assert set(qs.cenario) >= {"todas", "sem_erros", "sem_erros_suspeitos", "transitorios"}
