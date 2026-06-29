import unittest

from process_xbeach_retriever import run_xbeach_retriever as main_function


class Test(unittest.TestCase):
    """
    Test class for the XBeach retriever module.
    """

    def test_xyz(self):
        """
        test_xyz checks that the main function runs and returns a dict with a status.
        """
        res = main_function(
            lat_range=[44, 44.5],
            long_range=[12.2, 12.8],
            time_range=["2025-01-21T08:00:00", "2025-01-22T23:00:00"],
            out_format="geojson",
            debug=False,
            verbose=False
        )
        self.assertIsInstance(res, dict, "The main function should return a dictionary.")
        self.assertIn('status', res, "The result should contain a 'status' key.")


if __name__ == '__main__':
    unittest.main()
