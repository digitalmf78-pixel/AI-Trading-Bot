import unittest

class BacktestContractTests(unittest.TestCase):
    def test_eps_ratio_formula(self):
        self.assertAlmostEqual(400.0 * 16.0 / 20.0, 320.0)
    def test_sample_controls(self):
        pairs=[(64.34,71.46),(13.12,8.65),(9.12,11.55)]
        self.assertEqual(sum(cur<prev for prev,cur in pairs),1)
        self.assertEqual(sum(cur>=prev for prev,cur in pairs),2)

if __name__=="__main__": unittest.main()
