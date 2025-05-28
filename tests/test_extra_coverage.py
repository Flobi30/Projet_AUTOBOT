import sys, os
import pytest

def test_conftest_sys_path():
    root = os.path.abspath(os.path.dirname(__file__) + os.sep + "..")
    src  = os.path.join(root, "src")
    assert src in sys.path

from autobot.autobot_guardian import AutobotGuardian
def test_autobot_guardian_monitor():
    assert AutobotGuardian().monitor() is True
