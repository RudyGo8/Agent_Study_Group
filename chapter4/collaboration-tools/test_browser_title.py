import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


@pytest.mark.asyncio
async def test_browser_navigate_awaits_title():
    mock_page = AsyncMock()
    mock_page.title.return_value = "Test Page Title"
    mock_page.url = "http://example.com"
    mock_browser = AsyncMock()
    mock_browser.get_current_page.return_value = mock_page
    with patch("browser_tools.init_browser", return_value=mock_browser):
        from browser_tools import browser_navigate
        res = await browser_navigate("http://example.com")
    assert res["success"]
    assert res["title"] == "Test Page Title"
    mock_page.title.assert_called_once()


@pytest.mark.asyncio
async def test_browser_list_tabs_awaits_title():
    mock_page1 = AsyncMock()
    mock_page1.title.return_value = "Title 1"
    mock_page1.url = "http://example.com/1"
    mock_page2 = AsyncMock()
    mock_page2.title.return_value = "Title 2"
    mock_page2.url = "http://example.com/2"
    mock_browser = AsyncMock()
    mock_browser.get_pages.return_value = [mock_page1, mock_page2]
    with patch("browser_tools.init_browser", return_value=mock_browser):
        from browser_tools import browser_list_tabs
        res = await browser_list_tabs()
    assert res["success"]
    assert res["tabs"][0]["title"] == "Title 1"
    assert res["tabs"][1]["title"] == "Title 2"
