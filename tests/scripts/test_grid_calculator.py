"""
Tests for scripts/grid_calculator.py error message.

Validates that the KrakenPriceError message mentions both
get_price.py and requests for proper user guidance.
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))


class TestGridCalculatorErrorMessage:

    @patch('grid_calculator.get_current_price')
    def test_error_message_mentions_get_price_and_requests(self, mock_get_price, capsys):
        from grid_calculator import main
        from get_price import KrakenPriceError

        mock_get_price.side_effect = KrakenPriceError("Connection failed")

        with pytest.raises(SystemExit):
            main()

        captured = capsys.readouterr().out
        assert "get_price.py" in captured, (
            "Le message d'erreur doit mentionner get_price.py"
        )
        assert "requests" in captured, (
            "Le message d'erreur doit mentionner le module requests"
        )
