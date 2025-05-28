import pytest
from autobot.ecommerce.recycle import recycle_unsold

def test_recycle():
    assert recycle_unsold(7) is None

