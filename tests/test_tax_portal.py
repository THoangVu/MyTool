"""Unit tests for TaxPortalAutomation selectors and logic."""

import unittest
from unittest.mock import MagicMock
from src.tax_invoice_downloader.tax_portal import TaxPortalAutomation


class TestTaxPortalSelectors(unittest.TestCase):

    def setUp(self):
        self.mock_dm = MagicMock()
        self.automation = TaxPortalAutomation(download_manager=self.mock_dm)

    def test_get_export_xml_button_picks_last_candidate(self):
        """Verifies that between 'Xuất hóa đơn' and 'Xuất xml' (both having #Path_53113),
        the rightmost button (.last) is selected.
        """
        page = MagicMock()
        candidates_loc = MagicMock()
        candidates_loc.count.return_value = 2

        # First button is 'Xuất hóa đơn' (Excel), last button is 'Xuất xml' (XML)
        btn_excel = MagicMock(name="btn_excel")
        btn_xml = MagicMock(name="btn_xml")
        btn_xml.is_visible.return_value = True

        candidates_loc.last = btn_xml
        candidates_loc.first = btn_excel

        page.locator.return_value = candidates_loc

        chosen = self.automation._get_export_xml_button(page)
        self.assertEqual(chosen, btn_xml)
        self.assertNotEqual(chosen, btn_excel)

    def test_is_button_enabled(self):
        """Tests button state check under various conditions."""
        btn_none = None
        self.assertFalse(self.automation._is_button_enabled(btn_none))

        btn_hidden = MagicMock()
        btn_hidden.is_visible.return_value = False
        self.assertFalse(self.automation._is_button_enabled(btn_hidden))

        btn_disabled_attr = MagicMock()
        btn_disabled_attr.is_visible.return_value = True
        btn_disabled_attr.is_enabled.return_value = False
        btn_disabled_attr.get_attribute.side_effect = lambda attr: "ant-btn ant-btn-disabled" if attr == "class" else None
        self.assertFalse(self.automation._is_button_enabled(btn_disabled_attr))

        btn_enabled = MagicMock()
        btn_enabled.is_visible.return_value = True
        btn_enabled.is_enabled.return_value = True
        btn_enabled.get_attribute.side_effect = lambda attr: "ant-btn ButtonAnt__IconButton-sc-p5q16s-1 fRqwwC ant-btn-icon-only" if attr == "class" else None
        self.assertTrue(self.automation._is_button_enabled(btn_enabled))


if __name__ == "__main__":
    unittest.main()
