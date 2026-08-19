"""
测试套件：防止 ContextCompressor._no_compression 在搜索结果字典
包含 'content': None 时抛出 TypeError。
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from compression_strategies import ContextCompressor


def test_no_compression_handles_null_content():
    """
    确保 result['content'] 为 None 时 _no_compression 不抛 TypeError。
    """
    compressor = ContextCompressor.__new__(ContextCompressor)
    search_results = {
        'results': [
            {'title': 'Test', 'url': 'http://example.com', 'snippet': 'snippet', 'content': None}
        ]
    }
    compressed = compressor._no_compression(search_results)
    assert compressed.original_length == 0
    assert "Full Content:" in compressed.content
