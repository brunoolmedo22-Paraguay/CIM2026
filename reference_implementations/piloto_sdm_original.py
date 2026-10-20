"""Prueba de factibilidad: identificación multipunto de un SDM con IEC 61853 SUPSI.
No es el calibrador definitivo ni reemplaza el procedimiento clásico con datasheet.

Parámetros: IL_ref, I0_ref, Rs, Rsh_ref, a_ref.
a_ref equivale al producto n*Ns*k*Tref/q: no atribuir Ns o n específicos.
La traslación G,T sigue los supuestos del código SDM legado (De Soto / CEC).
"""
from scipy.optimize import least_squares, brentq
from scipy.special import lambertw
import numpy as np, csv, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
# Lectura de tabla derivada del laboratorio, con referencia explícita al XLSX original
with (ROOT/'input/SUPSI/derived/lab_IEC61853_matrix_long.csv').open(encoding='utf8',newline='') as f:
    laboratory=list(csv.DictReader(f))
TREF=298.15
KEV=8.617333262145e-5
EG=1.121
DEGDT=-0.0002677
ALPHA=0.046/100.*9.486848514934435  # A/°C from laboratory data

# Matrices indexadas explícitamente. El texto '32' es un marcador de falta de medición.
obs=[(r['variable'],float(r['irradiance_poa_Wm2']),float(r['temperature_module_C']),float(r['measured_value'])) for r in laboratory]
assert len(obs)==66, len(obs)
obs_by={(name,G,T):v for name,G,T,v in obs}
conds=sorted(set((G,T) for _,G,T,_ in obs))

# 5 parámetros reales, sin introducir artificialmente Ns.
def operating(x,G,T):
    IL_ref,log_I0,Rs,log_Rsh,a_ref=x
    I0_ref=10**log_I0
    Rsh_ref=10**log_Rsh
    Tk=T+273.15
    IL=(G/1000.)*(IL_ref+ALPHA*(T-25.))
    I0=I0_ref*(Tk/TREF)**3*np.exp(EG/(KEV*TREF) - (EG*(1+DEGDT*(T-25.)))/(KEV*Tk))
    return max(IL,0), I0, Rs, Rsh_ref*1000./G, a_ref*(Tk/TREF)

def current(V,p):
    IL,I0,Rs,Rsh,a=p
    d=a*(Rs+Rsh)
    lz=np.log(Rs*I0*Rsh/d)+Rsh*(Rs*(IL+I0)+V)/d
    # typical lz < 500; numerical fallback for super-high values
    w=np.real(lambertw(np.exp(np.minimum(lz,500)))) if lz<500 else (lz-np.log(lz)+np.log(lz)/lz)
    return (Rsh*(IL+I0)-V)/(Rs+Rsh)-(a/Rs)*w

def voc(p):
    IL,I0,Rs,Rsh,a=p
    hi=a*np.log1p(IL/I0)*1.05
    return brentq(lambda V:current(V,p),0,hi,xtol=1e-9)

def mpp(p,vo):
    from scipy.optimize import minimize_scalar
    rr=minimize_scalar(lambda v:-v*current(v,p),bounds=(0,vo),method='bounded',options={'xatol':1e-6})
    return -float(rr.fun)

# Se optimiza con los tres conjuntos experimentales, normalizando por escala STC.
scale={'Pmp':285.6859174344,'Isc':9.4868485149,'Voc':39.7147312307}
def res(x):
    pred={}
    try:
        for G,T in conds:
            p=operating(x,G,T)
            v=voc(p)
            pred[(G,T)]={'Pmp':mpp(p,v),'Isc':current(0.,p),'Voc':v}
        return np.array([(pred[(G,T)][name]-val)/scale[name] for name,G,T,val in obs])
    except (ValueError,OverflowError,FloatingPointError):
        return np.full(len(obs),1e3)

lo=[8,-15,0.0001,1.5,.8]
hi=[12,-3,3.0,5.5,3.4]
starts=[[9.5,-9,.4,2.7,1.8],[9.6,-10,.6,3.3,2.1],[9.7,-8,.2,2.0,1.2]]
solutions=[]
for seed in starts:
    sol=least_squares(res,seed,bounds=(lo,hi),max_nfev=350,method='trf',ftol=1e-10,xtol=1e-10,gtol=1e-10)
    solutions.append(sol)
sol=min(solutions,key=lambda s:np.sum(s.fun**2))
x=sol.x
print('FIT',{ 'success':sol.success, 'message':sol.message,'nfev':sol.nfev,'loss':float(np.sum(sol.fun**2))})
print('PARAMETERS',{'IL_ref_A':x[0], 'I0_ref_A':10**x[1],'Rs_ohm':x[2], 'Rsh_ref_ohm':10**x[3],'a_ref_V':x[4]})
for typ in ['Pmp','Isc','Voc']:
    subset=[(G,T,y) for name,G,T,y in obs if name==typ]
    y=np.array([v for G,T,v in subset]); yp=np.array([({'Pmp':lambda:p_mpp(), 'Isc':lambda:current(0.,p),'Voc':lambda:v})[typ]() for G,T,val in []]) if False else []
    for G,T,val in subset:
        p=operating(x,G,T);v=voc(p)
        yp.append({'Pmp':mpp(p,v),'Isc':current(0.,p),'Voc':v}[typ])
    yp=np.array(yp)
    print('LAB',typ, 'n',len(y),'MAE',float(np.mean(np.abs(yp-y))),'RMSE',float(np.sqrt(np.mean((yp-y)**2))),'MAX_ABS',float(np.max(np.abs(yp-y))))

# Comparación FUERA del laboratorio: enero 2019, selección determinista 1 de cada 25
# Tbom es temperatura posterior de módulo, NO la temperatura exacta de la célula.
# Solamente diagnóstico exploratorio, no validación científica definitiva.
candidates=[]
with (ROOT/'input/SUPSI/raw/field_2019/2019_01.csv').open(newline='',encoding='utf-8-sig') as f:
    reader=csv.DictReader(f,delimiter=';')
    for row in reader:
        row={k.strip():v.strip() for k,v in row.items()}
        try:
            G=float(row['Gpoa']);T=float(row['Tbom']);P=float(row['Pm'])
            if 100<=G<=1100 and np.isfinite(G*T*P) and -15<T<90:
                candidates.append((G,T,P))
        except (ValueError,TypeError):pass
sample=candidates[::25]
pe=[]
for G,T,P in sample:
    pp=operating(x,G,T);vo=voc(pp);pe.append(mpp(pp,vo))
y=np.array([a[2] for a in sample]);pred=np.array(pe)
print('FIELD_PILOT_BACK_TEMPERATURE_AS_CELL',{'n':len(sample),'MAE_W':float(np.mean(np.abs(pred-y))),'RMSE_W':float(np.sqrt(np.mean((pred-y)**2))),'MBE_W':float(np.mean(pred-y)),'note':'exploratory: uses Tbom as Tc; not final validation'})

artifact={'source':'SUPSI IEC61853-1&2', 'fit':{'success':bool(sol.success),'nfev':int(sol.nfev),'sum_normalized_squared_residuals':float(np.sum(sol.fun**2))},'parameters':{'IL_ref_A':float(x[0]),'I0_ref_A':float(10**x[1]),'Rs_ohm':float(x[2]),'Rsh_ref_ohm':float(10**x[3]),'a_ref_V':float(x[4])},'label':'PILOT ONLY; not demonstrated unique; cell temperature correction pending; model translation assumptions borrowed from legacy code'}
(HERE/'piloto_sdm_reproducido.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),encoding='utf-8')
print('SEEDS',[(float(np.sum(s.fun**2)),[float(xx) for xx in s.x]) for s in solutions])
sv=np.linalg.svd(sol.jac,compute_uv=False)
print('JACOBIAN_SINGULAR_VALUES',[float(v) for v in sv], 'CONDITION',float(sv[0]/sv[-1]))
ps=operating(x,1000,25)
vs=voc(ps)
print('STC_PREDICTED',{'Pmp_W':mpp(ps,vs),'Isc_A':current(0.,ps),'Voc_V':vs})
# Comparación exploratoria adicional con 4 formulaciones: mismo subconjunto del campo,
# misma estimación directa de temperatura (Tbom ~= Tc), sin recalibrar con datos de campo.
# Coeficientes Huld c-Si Current documentados por PVGIS JRC.
k=[-0.017237,-0.040465,-0.004702,0.000149,0.000170,0.000005]
def baseline_powers(G,T):
    g=G/1000.;dt=T-25.;lnG=np.log(g)
    p0=285.68591743441357*g
    ptemp=p0*(1-.00405*dt)
    pr=p0*(1+k[0]*lnG+k[1]*lnG**2+k[2]*dt+k[3]*dt*lnG+k[4]*dt*lnG**2+k[5]*dt**2)
    return p0,ptemp,pr
ys=np.array([c[2] for c in sample])
bases=np.array([baseline_powers(G,T) for G,T,P in sample])
for name,z in zip(['lineal_G','termico_gamma','Huld_PVGIS_cSi','SDM_multipunto'],[*bases.T,pred]):
    print('FIELD_COMPARE',name,{'n':len(ys),'MAE_W':float(np.mean(np.abs(z-ys))),'RMSE_W':float(np.sqrt(np.mean((z-ys)**2))),'MBE_W':float(np.mean(z-ys))})
