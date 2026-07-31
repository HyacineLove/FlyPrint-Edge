import unittest

from print_quota import quota_usage


class PrintQuotaTests(unittest.TestCase):
    def test_full_duplex_color_usage_matches_cloud(self):
        self.assertEqual(
            {"impressions": 6, "sheets": 4, "points": 8},
            quota_usage(3, 2, "longedge", "color"),
        )

    def test_partial_duplex_color_usage_keeps_copy_boundaries(self):
        self.assertEqual(
            {"impressions": 4, "sheets": 3, "points": 6},
            quota_usage(3, 2, "longedge", "color", impressions_completed=4),
        )

    def test_rejects_impossible_actual_impression_count(self):
        with self.assertRaises(ValueError):
            quota_usage(3, 2, "simplex", "mono", impressions_completed=7)


if __name__ == "__main__":
    unittest.main()
