"""pytest 公共夹具。"""
import time

import pytest

import app.guards as guards


@pytest.fixture(autouse=True)
def _restore_clock():
    """每个测试后恢复真实时钟，避免 mock 的时间污染其他测试。"""
    original = guards._clock
    yield
    guards._clock = original
