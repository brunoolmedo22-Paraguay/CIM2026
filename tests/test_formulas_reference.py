import sys,unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'reference_implementations'))
from m1_m2_m3_reference import m1_irradiance,m2_pvwatts_dc,m3_huld
from field_reader_reference import read_month

class FormulaReferenceTests(unittest.TestCase):
    def test_stc_all(self):
        self.assertAlmostEqual(float(m1_irradiance([1000],285.6859)[0]),285.6859)
        self.assertAlmostEqual(float(m2_pvwatts_dc([1000],[25],285.6859,-.00405)[0]),285.6859)
        self.assertAlmostEqual(float(m3_huld([1000],[25],285.6859)[0]),285.6859)
    def test_zero_and_thermal(self):
        for f in (lambda:m1_irradiance([0],285.6859),lambda:m2_pvwatts_dc([0],[30],285.6859,-.00405),lambda:m3_huld([0],[30],285.6859)):
            self.assertEqual(float(f()[0]),0.)
        self.assertLess(float(m2_pvwatts_dc([1000],[55],285.6859,-.00405)[0]),float(m2_pvwatts_dc([1000],[25],285.6859,-.00405)[0]))
    def test_2019_field_mapping(self):
        d=read_month(ROOT/'input/SUPSI/raw/field_2019/2019_01.csv')
        self.assertIn('g_poa_Wm2',d.columns)
        self.assertIn('ghi_Wm2',d.columns)
        self.assertIn('p_mpp_measured_W',d.columns)
        self.assertTrue(d.timestamp.notna().any())
if __name__=='__main__':unittest.main()
