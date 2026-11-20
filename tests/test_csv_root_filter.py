"""Regression: Cboe Root=All NVDA exports must not mix B1VDA into NVDA.

All CSV inputs synthetic, no Cboe download, no external dependencies.
"""
import csv
import io
import unittest

from cboe_csv_import import InvalidCboeCSV, csv_to_snapshot


HEADER = ["Expiration Date", "Calls", "Gamma", "Volume", "Open Interest",
          "Strike", "Puts", "Gamma", "Volume", "Open Interest"]


def payload(*rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["NVIDIA CORPORATION (NVDA)", "Last: 186.22", "Change: +1.20"])
    writer.writerow(["Date: November 20, 2026, 11:13 AM GMT+1"])
    writer.writerow(HEADER)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def pair(root, *, gamma="0.012", strike="135.00"):
    return [
        "Fri Nov 20 2026", root + "261120C00135000",
        gamma, "10", "100", strike,
        root + "261120P00135000", gamma, "20", "200",
    ]


class EquityRootFilterTests(unittest.TestCase):
    def test_root_all_excludes_b1vda_and_keeps_only_standard_nvda(self):
        doc = csv_to_snapshot(payload(pair("B1VDA", gamma="-0.03"),
                                      pair("NVDA")), "NVDA")
        self.assertEqual(
            [x["option"] for x in doc["data"]["options"]],
            ["NVDA261120C00135000", "NVDA261120P00135000"],
        )
        provenance = doc["_import_provenance"]
        self.assertEqual(provenance["contracts"], 2)
        self.assertEqual(provenance["unsupported_contracts_excluded"], 2)
        self.assertEqual(provenance["unsupported_contract_roots"], {"B1VDA": 2})

    def test_root_nvda_only_needs_no_filtering(self):
        doc = csv_to_snapshot(payload(pair("NVDA")), "NVDA")
        self.assertEqual(len(doc["data"]["options"]), 2)
        self.assertEqual(doc["_import_provenance"]["unsupported_contracts_excluded"], 0)
        self.assertEqual(doc["_import_provenance"]["unsupported_contract_roots"], {})

    def test_other_roots_only_are_rejected_instead_of_silent_empty_plot(self):
        with self.assertRaisesRegex(InvalidCboeCSV, "nessun contratto standard"):
            csv_to_snapshot(payload(pair("B1VDA")), "NVDA")

    def test_bad_own_root_contract_remains_an_error(self):
        bad = pair("NVDA")
        bad[1] = "NVDA261120C0013500"  # malformed strike code, not another root
        with self.assertRaisesRegex(InvalidCboeCSV, "opzione incompatibile"):
            csv_to_snapshot(payload(bad), "NVDA")

    def test_gamma_validation_still_applies_to_standard_nvda(self):
        with self.assertRaisesRegex(InvalidCboeCSV, "non negativi"):
            csv_to_snapshot(payload(pair("NVDA", gamma="-0.03")), "NVDA")


if __name__ == "__main__":
    unittest.main()
