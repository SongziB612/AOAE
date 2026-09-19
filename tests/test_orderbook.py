import unittest

from aoae.orderbook import apply_book_message, empty_book, top_of_book


class OrderBookTests(unittest.TestCase):
    def test_snapshot_and_incremental_updates(self):
        books = {"t": empty_book()}
        apply_book_message({"event_type": "book", "asset_id": "t", "bids": [{"price": ".4", "size": "8"}], "asks": [{"price": ".6", "size": "7"}]}, books)
        self.assertEqual(top_of_book(books["t"])["ask"], .6)
        apply_book_message({"event_type": "price_change", "price_changes": [{"asset_id": "t", "side": "SELL", "price": ".55", "size": "5"}]}, books)
        self.assertEqual(top_of_book(books["t"])["ask"], .55)
        apply_book_message({"event_type": "price_change", "price_changes": [{"asset_id": "t", "side": "SELL", "price": ".55", "size": "0"}]}, books)
        self.assertEqual(top_of_book(books["t"])["ask"], .6)

    def test_unknown_token_is_ignored(self):
        books = {"t": empty_book()}
        apply_book_message({"event_type": "book", "asset_id": "other", "bids": [], "asks": []}, books)
        self.assertEqual(top_of_book(books["t"]), {"bid": None, "bid_size": None, "ask": None, "ask_size": None})


if __name__ == "__main__":
    unittest.main()
