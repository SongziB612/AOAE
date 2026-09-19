import unittest

from aoae.basket import evaluate_complete_set


def book(bid, ask, size=10):
    return {"bids": [{"price": str(bid), "size": str(size)}], "asks": [{"price": str(ask), "size": str(size)}]}


class BasketTests(unittest.TestCase):
    def test_taker_opportunity_is_fee_adjusted(self):
        result = evaluate_complete_set([book(.39, .40), book(.49, .50)], [.04, .04])
        self.assertTrue(result["taker"]["profitable_before_external_costs"])
        self.assertAlmostEqual(result["taker"]["net_payoff"], .0804)

    def test_maker_fill_is_never_claimed_as_guaranteed(self):
        result = evaluate_complete_set([book(.4, .41), book(.5, .51)], [0, 0])
        self.assertEqual(result["maker"]["payoff_if_every_leg_fills"], .1)
        self.assertFalse(result["maker"]["all_legs_fill_guaranteed"])

    def test_one_sided_book_fails(self):
        with self.assertRaises(ValueError):
            evaluate_complete_set([book(.4, .5), {"bids": [], "asks": []}], [0, 0])


if __name__ == "__main__":
    unittest.main()
