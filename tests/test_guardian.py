import pytest
from autobot.autobot_guardian import AutobotGuardian

def test_guardian_init():
    g = AutobotGuardian()
    assert hasattr(g, 'check_logs')

