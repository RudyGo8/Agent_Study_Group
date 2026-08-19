import pytest
from tau_bench.model_utils.api.cache import (
    cache,
    cache_call_w_dedup,
    conditions,
    hash_item,
)


class SameReprKey:
    """可哈希键，其 repr 刻意不携带任何身份信息。"""

    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return 0

    def __eq__(self, other):
        return isinstance(other, SameReprKey) and self.value == other.value

    def __repr__(self):
        return "SameReprKey()"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    conditions.clear()
    yield
    cache.clear()
    conditions.clear()


def test_hash_item_dict_different_values():
    """同一键名下的不同值不能共享同一规范化身份。"""
    dict1 = {"a": 1}
    dict2 = {"a": 2}
    assert hash_item(dict1) != hash_item(dict2)


def test_hash_item_dict_different_key_value_pairs():
    """键值互换后字典身份必须改变。"""
    dict1 = {"a": 1, "b": 2}
    dict2 = {"a": 2, "b": 1}
    assert hash_item(dict1) != hash_item(dict2)


def test_hash_item_dict_nested_different_values():
    """递归嵌套值中的差异必须仍可被观察到。"""
    dict1 = {"a": {"items": [1, {"value": "first"}]}}
    dict2 = {"a": {"items": [1, {"value": "second"}]}}
    assert hash_item(dict1) != hash_item(dict2)


def test_hash_item_dict_heterogeneous_keys_is_order_independent():
    """混合类型的键做规范化时必须与插入顺序无关。"""
    dict1 = {1: "integer", "1": "string", (1,): "tuple"}
    dict2 = {(1,): "tuple", "1": "string", 1: "integer"}
    assert hash_item(dict1) == hash_item(dict2)


def test_cache_dict_same_repr_keys_is_order_independent():
    """即使键的排序身份冲突，相等的字典仍会去重。"""
    calls = 0
    first_key = SameReprKey("first")
    second_key = SameReprKey("second")
    dict1 = {first_key: 1, second_key: 2}
    dict2 = {second_key: 2, first_key: 1}

    @cache_call_w_dedup
    def lookup(value):
        nonlocal calls
        calls += 1
        return calls, value

    assert dict1 == dict2
    assert hash_item(dict1) == hash_item(dict2)
    assert lookup(dict1)[0] == 1
    assert lookup(dict2)[0] == 1
    assert calls == 1


def test_hash_item_set_same_repr_members_is_order_independent():
    """即使成员的排序身份冲突，相等的集合仍规范化为同一结果。"""
    first = SameReprKey("first")
    second = SameReprKey("second")
    set1 = {first, second}
    set2 = {second, first}

    assert set1 == set2
    assert hash_item(set1) == hash_item(set2)


def test_hash_item_dict_distinguishes_heterogeneous_key_types():
    """文本上相似但类型不同的键不能发生碰撞。"""
    assert hash_item({1: "value"}) != hash_item({"1": "value"})


@pytest.mark.parametrize(
    ("item1", "item2"),
    [
        ([1, 2], (1, 2)),
        ({1, 2}, (1, 2)),
        ({"a": 1}, (("a", 1),)),
    ],
)
def test_hash_item_preserves_container_type(item1, item2):
    """list/tuple、set/tuple、dict/tuple 输入必须保持互不相同。"""
    assert hash_item(item1) != hash_item(item2)


def test_cache_distinguishes_same_named_function_instances():
    """同名但不同的可调用对象绝不能共享缓存结果。"""
    def make_lookup(prefix):
        @cache_call_w_dedup
        def lookup(value):
            return prefix, value

        return lookup

    lookup_a = make_lookup("a")
    lookup_b = make_lookup("b")

    assert lookup_a(7) == ("a", 7)
    assert lookup_b(7) == ("b", 7)


def test_cache_distinguishes_nan_dictionary_keys():
    """文本相同但互不相等的 NaN 键不能共享缓存结果。"""
    calls = 0

    @cache_call_w_dedup
    def lookup(value):
        nonlocal calls
        calls += 1
        return calls, value

    first_result = lookup({float("nan"): "value"})
    second_result = lookup({float("nan"): "value"})

    assert first_result[0] == 1
    assert second_result[0] == 2
