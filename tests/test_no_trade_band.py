import unittest
from aoae.no_trade_band import filter_target
from aoae.shadow_accounting import new_account


class NoTradeBandTests(unittest.TestCase):
    def setUp(self):
        self.a = new_account(10000, 1000)
        self.a.update(cash='5000', positions={'A':500})
        self.prices = {'A':10, 'B':10}
        self.target = {'A':.5,'B':0}

    def test_small_drift_skipped_without_mutation(self):
        target, reason = filter_target(self.a,{'A':.52,'B':0},self.target,self.prices,.05)
        self.assertIsNone(target)
        self.assertEqual(reason,'SKIP_SMALL_DRIFT')
        self.assertEqual(self.a['positions'],{'A':500})

    def test_new_asset_and_exit_not_suppressed(self):
        for target in ({'A':.5,'B':.01},{'A':0,'B':0}):
            self.assertEqual(filter_target(self.a,target,self.target,self.prices,.1)[0],target)

    def test_risk_reduction_not_suppressed(self):
        target = {'A':.49,'B':0}
        self.assertEqual(filter_target(self.a,target,self.target,self.prices,.1)[1],'RISK_REDUCTION')

    def test_zero_band_and_initial_bypass(self):
        self.assertEqual(filter_target(self.a,self.target,self.target,self.prices,0)[0],self.target)
        self.assertEqual(filter_target(self.a,self.target,None,self.prices,.1)[0],self.target)

    def test_pause_bypasses_filter(self):
        self.a['paused']=True
        self.assertIsNotNone(filter_target(self.a,self.target,self.target,self.prices,.1)[0])

    def test_large_drift_trades(self):
        self.assertEqual(filter_target(self.a,{'A':.7,'B':0},self.target,self.prices,.05)[1],'OUTSIDE_BAND')

    def test_invalid_rejected(self):
        for band in (-.1,float('nan'),2):
            with self.assertRaises(ValueError):
                filter_target(self.a,self.target,self.target,self.prices,band)
        with self.assertRaises(ValueError):
            filter_target(self.a,{'A':2,'B':0},self.target,self.prices,.05)
