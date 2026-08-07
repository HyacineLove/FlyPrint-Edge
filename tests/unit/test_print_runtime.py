import unittest

from print_runtime import build_print_request


class DummyConfig:
    def get_printer_by_id(self, printer_id):
        return {
            "id": printer_id,
            "name": "HP",
            "printer_uuid": "urn:uuid:printer-1",
            "ipp_uri": "ipp://printer.local/ipp/print",
        }

    def get_full_config(self):
        return {
            "settings": {
                "default_paper_size": "Letter",
                "default_scale_percent": 120,
            }
        }


class PrintRuntimeTests(unittest.TestCase):
    def test_build_print_request_applies_edge_layout_defaults(self):
        request = build_print_request(
            DummyConfig(),
            job_id="job-1",
            printer_id="printer-1",
            file_path=None,
            source_name="document.pdf",
            print_options={"copies": 1, "duplex": "simplex", "color_mode": "color"},
        )

        self.assertEqual("Letter", request.options.paper_size)
        self.assertEqual("portrait", request.options.orientation)
        self.assertEqual(120, request.options.scale_percent)


if __name__ == "__main__":
    unittest.main()
