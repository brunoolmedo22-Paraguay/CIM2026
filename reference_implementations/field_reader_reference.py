"""Ejemplo de lectura sin corregir ni imputar silenciosamente mediciones SUPSI."""
from pathlib import Path
import pandas as pd

MAP={'Pm':'p_mpp_measured_W','Voc':'voc_measured_V','Isc':'isc_measured_A',
     'Tbom':'temp_back_C','Gpoa':'g_poa_Wm2',
     'Gglob_hor':'ghi_Wm2','Gdiff_hor':'dhi_Wm2',
     'AIR_TEMP':'temp_ambient_C','WIND_SPEED':'wind_speed_ms','RH_AIR':'relative_humidity_pct'}

def read_month(p: str | Path) -> pd.DataFrame:
    df=pd.read_csv(p,sep=';',encoding='utf-8-sig')
    df.columns=df.columns.str.strip()
    mandatory={'Date','Time','Pm','Gpoa','Tbom','AIR_TEMP','WIND_SPEED'}
    missing=mandatory-set(df.columns)
    if missing:raise ValueError(f'Columnas SUPSI ausentes: {sorted(missing)}')
    df['timestamp']=pd.to_datetime(df['Date'].astype(str).str.strip()+' '+df['Time'].astype(str).str.strip(),
                                   format='%d.%m.%Y %H:%M:%S',errors='coerce')
    for col in MAP:
        if col in df:df[col]=pd.to_numeric(df[col],errors='coerce')
    return df.rename(columns=MAP)
