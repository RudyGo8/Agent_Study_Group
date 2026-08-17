"""--only 参数解析：非法题号应干净退出（SystemExit），而非 ValueError 栈。"""
import pytest

from demo import _parse_only


def test_parse_only_valid():
    assert _parse_only("1,5,10") == {1, 5, 10}


def test_parse_only_empty_means_all():
    assert _parse_only("") is None
    assert _parse_only(None) is None


def test_parse_only_non_integer_clean_exit():
    with pytest.raises(SystemExit, match="整数"):
        _parse_only("1,2x")


def test_parse_only_unknown_id_clean_exit():
    with pytest.raises(SystemExit, match="未知题号"):
        _parse_only("999")
