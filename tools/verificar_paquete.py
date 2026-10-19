"""Comprobación básica de integridad del handoff, reproducible sin Streamlit."""
from pathlib import Path
import csv,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
raw=ROOT/'input/SUPSI/raw/field_2019'
months=list(sorted(raw.glob('2019_*.csv')))
assert len(months)==6, f'se requieren 6 meses, hay {len(months)}'
assert (ROOT/'input/SUPSI/raw/laboratory/IEC61853_1-2.xlsx').exists()
assert (ROOT/'legacy_core/simulation/solver.py').exists()
assert (ROOT/'reference_implementations/m1_m2_m3_reference.py').exists()
with (ROOT/'input/SUPSI/derived/lab_IEC61853_matrix_long.csv').open(encoding='utf8',newline='') as f:
 rows=list(csv.DictReader(f))
assert len(rows)==66
assert {v:sum(r['variable']==v for r in rows) for v in ('Pmp','Isc','Voc')}=={'Pmp':22,'Isc':22,'Voc':22}
module=json.loads((ROOT/'input/SUPSI/derived/SUPSI_module_experimental.json').read_text(encoding='utf8'))
assert all(module[k] is None for k in ('manufacturer','commercial_model','vmp_stc_V','imp_stc_A','series_cell_count'))
n=0
for p in months:
 with p.open(encoding='utf-8-sig',newline='') as f:
  rd=csv.DictReader(f,delimiter=';')
  assert {'Date',' Time',' Pm',' Gpoa'}.issubset(set(rd.fieldnames))
  n+=sum(1 for _ in rd)
assert n>10000
print(f'OK: {len(months)} CSV SUPSI, {n} filas, 66 medidas laboratorio, referencias y fuentes existentes')
