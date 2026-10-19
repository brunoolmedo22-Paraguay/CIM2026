import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def lab():
    from cim26.data.supsi_lab import read_iec61853_xlsx
    return read_iec61853_xlsx()


@pytest.fixture(scope="session")
def supsi_module():
    from cim26.data.supsi_lab import supsi_module_spec
    return supsi_module_spec()


@pytest.fixture(scope="session")
def supsi_cal(lab, supsi_module):
    from cim26.calibration.multipoint import MultipointConfig, calibrate_multipoint
    return calibrate_multipoint(lab.long, supsi_module, MultipointConfig(n_starts=2))


@pytest.fixture(scope="session")
def field():
    from cim26.data.supsi_field import load_field
    return load_field()


@pytest.fixture(scope="session")
def small_run(tmp_path_factory):
    from cim26.experiment.config import ExperimentConfig
    from cim26.experiment.runner import run_experiment
    cfg = ExperimentConfig(months=("2019_02",), repetitions=3, scaling_sizes=(200,), bootstrap_B=300,
                           sensitivity_delta_t=(0.0, 3.0), calibration={**ExperimentConfig().calibration, "n_starts": 2},
                           tracemalloc_pass=False, label="teste")
    return run_experiment(cfg, tmp_path_factory.mktemp("runs"), use_lock=True)
