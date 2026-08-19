"""
测试套件：防止 WebTools.search_web 在 fetch_webpage 返回的字典
包含 'content': None 时抛出 TypeError。
"""

import os
import sys
from unittest.mock import MagicMock

sys.modules['html2text'] = MagicMock()

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from web_tools import WebTools


def test_search_web_handles_null_page_content():
    """
    确保 page_content['content'] 为 None 时 search_web 仍能正确计算 content_length。
    """
    tool = WebTools.__new__(WebTools)
    tool.serper_api_key = "dummy"
    tool.fetch_webpage = MagicMock(return_value={'content': None, 'success': True})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        'organic': [
            {'title': 'Example', 'link': 'http://example.com', 'snippet': 'Test snippet'}
        ]
    }
    
    import requests
    requests.post = MagicMock(return_value=mock_resp)

    res = tool.search_web("test query", num_results=1)
    assert res['num_results'] == 1
    assert res['results'][0]['content_length'] == 0

def test_fetch_webpage_title_with_nested_elements():
    """
    确保 title 标签内含嵌套 HTML 元素时 fetch_webpage 仍能正确提取标题文本。
    """
    html_content = "<html><head><title>Report <span>2026</span></title></head><body><p>Test content</p></body></html>"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html_content
    mock_resp.raise_for_status = MagicMock()

    import requests
    requests.get = MagicMock(return_value=mock_resp)

    tool = WebTools.__new__(WebTools)
    tool.page_cache = {}
    tool.html_converter = MagicMock()
    tool.html_converter.handle.return_value = "Test content"

    res = tool.fetch_webpage("http://example.com/report")
    assert res['title'] == "Report 2026"
