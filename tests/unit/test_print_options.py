import unittest

from print_options import normalize_print_options, to_cloud_duplex


class PrintOptionsTests(unittest.TestCase):
    def test_cloud_single_maps_to_simplex(self):
        options = normalize_print_options(
            {"duplex_mode": "single", "color_mode": "mono"}
        )
        self.assertEqual(options["duplex"], "simplex")
        self.assertEqual(options["color_mode"], "mono")

    def test_cloud_duplex_maps_to_long_edge(self):
        options = normalize_print_options(
            {"duplex_mode": "duplex", "color_mode": "color"}
        )
        self.assertEqual(options["duplex"], "longedge")
        self.assertEqual(options["color_mode"], "color")

    def test_frontend_values_are_sent_using_cloud_schema(self):
        self.assertEqual(to_cloud_duplex("simplex"), "single")
        self.assertEqual(to_cloud_duplex("longedge"), "duplex")
        self.assertEqual(to_cloud_duplex("shortedge"), "duplex")

    def test_landscape_paper_uses_the_same_ipp_media_as_portrait(self):
        from printing.domain import PrintOptions

        self.assertEqual(
            PrintOptions(paper_size="A4 (横向)").ipp_media,
            PrintOptions(paper_size="A4").ipp_media,
        )


if __name__ == "__main__":
    unittest.main()
