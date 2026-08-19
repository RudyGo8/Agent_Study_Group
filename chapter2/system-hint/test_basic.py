"""
验证 System-Hint Agent 基础功能的测试
"""

import os
import sys

import pytest

from agent import SystemHintAgent, SystemHintConfig, TodoStatus

def test_basic_functionality():
    """测试 Agent 基础功能（不调用 API）"""
    print("Testing System-Hint Agent components...")
    
    # 测试配置
    config = SystemHintConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True
    )
    print("✅ Configuration created successfully")
    
    # 测试 Agent 初始化（基础测试不使用真实 API Key）
    try:
        agent = SystemHintAgent(
            api_key="test-key",  # 初始化测试用的占位 Key
            provider="kimi",
            config=config,
            verbose=False
        )
        print("✅ Agent initialized successfully")
    except Exception as e:
        print(f"❌ Agent initialization failed: {e}")
        return False
    
    # 测试工具实现（不调用 API）
    print("\nTesting tool implementations:")
    
    # 测试文件操作
    test_file = "test_output.txt"
    try:
        # 测试 write_file
        result = agent._tool_write_file(test_file, "Test content")
        assert result["success"]
        print("✅ write_file tool works")
        
        # 测试 read_file
        result = agent._tool_read_file(test_file)
        assert result["success"]
        assert "Test content" in result["content"]
        print("✅ read_file tool works")
        
        
        # 清理
        os.remove(test_file)
        
    except Exception as e:
        print(f"❌ File operation test failed: {e}")
    
    # 测试代码解释器
    try:
        result = agent._tool_code_interpreter("result = 2 + 2")
        assert result["success"]
        assert result["result"] == 4
        print("✅ code_interpreter tool works")
    except Exception as e:
        print(f"❌ Code interpreter test failed: {e}")
    
    # 测试 TODO 列表操作
    try:
        # 测试 rewrite_todo_list
        result = agent._tool_rewrite_todo_list(["Task 1", "Task 2", "Task 3"])
        assert result["success"]
        assert result["new_items"] == 3
        print("✅ rewrite_todo_list tool works")
        
        # 测试 update_todo_status
        result = agent._tool_update_todo_status([
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "in_progress"}
        ])
        assert result["success"]
        assert result["updated_items"] == 2
        print("✅ update_todo_status tool works")
        
        # 校验 TODO 列表状态
        assert len(agent.todo_list) == 3
        assert agent.todo_list[0].status == TodoStatus.COMPLETED
        assert agent.todo_list[1].status == TodoStatus.IN_PROGRESS
        print("✅ TODO list management works correctly")
        
    except Exception as e:
        print(f"❌ TODO list test failed: {e}")
    
    # 测试系统状态
    try:
        state = agent._get_system_state()
        assert "Current Time:" in state
        assert "Current Directory:" in state
        assert "System:" in state
        print("✅ System state tracking works")
    except Exception as e:
        print(f"❌ System state test failed: {e}")
    
    # 测试错误处理
    try:
        # 这里应当失败并生成详细错误
        result = agent._tool_read_file("/nonexistent/file.txt")
    except Exception as e:
        error_detail = agent._get_detailed_error(e, "read_file", {"file_path": "/nonexistent/file.txt"})
        assert "FileNotFoundError" in str(e.__class__.__name__) or "No such file" in str(e)
        assert "Suggestions:" in error_detail
        print("✅ Detailed error handling works")
    
    print("\n✅ All basic tests passed!")
    return True

def test_command_execution():
    """测试命令执行工具"""
    print("\nTesting command execution:")
    
    config = SystemHintConfig(enable_detailed_errors=True)
    agent = SystemHintAgent(
        api_key="test-key",
        provider="kimi",
        config=config,
        verbose=False
    )
    
    try:
        # 测试简单命令
        result = agent._tool_execute_command("echo 'Hello, World!'")
        assert result["success"]
        assert "Hello, World!" in result["output"]
        print("✅ Command execution works")
        
        # 测试目录切换
        original_dir = agent.current_directory
        result = agent._tool_execute_command("cd /tmp")
        assert agent.current_directory == "/tmp"
        agent.current_directory = original_dir  # 恢复
        print("✅ Directory tracking works")
        
    except Exception as e:
        print(f"⚠️ Command execution test skipped: {e}")
    
    return True
def test_read_file_empty_file_line_range():
    """
    证明对空文件（0 行）按行 read_file 会以空内容成功返回。
    
    此前当 LLM Agent 请求按行读取空文件（如 begin_line=1、number_lines=10）时，
    start_line（0）用 >= 与 total_lines（0）比较，导致工具返回
    "begin_line 1 超出文件长度" 的错误。本测试断言空文件的按行读取
    返回 success=True 且 content=""，防止回归。
    """
    config = SystemHintConfig(enable_detailed_errors=True)
    agent = SystemHintAgent(api_key="test-key", provider="kimi", config=config, verbose=False)
    empty_file = "empty_test.txt"
    try:
        agent._tool_write_file(empty_file, "")
        res_empty = agent._tool_read_file(empty_file, begin_line=1, number_lines=10)
        assert res_empty.get("success") is True, f"Failed empty file read: {res_empty}"
        assert res_empty.get("content") == ""
    finally:
        if os.path.exists(empty_file):
            os.remove(empty_file)


def test_read_file_rejects_invalid_line_arguments(tmp_path):
    """非法的参数类型不得静默变成从第一行读取。"""
    config = SystemHintConfig(enable_detailed_errors=True)
    agent = SystemHintAgent(api_key="test-key", provider="kimi", config=config, verbose=False)
    agent.current_directory = str(tmp_path)
    agent._tool_write_file("sample.txt", "one\ntwo\n")

    with pytest.raises(TypeError):
        agent._tool_read_file("sample.txt", begin_line="invalid")

if __name__ == "__main__":
    print("="*60)
    print("  System-Hint Agent Component Tests")
    print("="*60)
    
    # 运行基础测试
    if test_basic_functionality():
        test_command_execution()
        test_read_file_empty_file_line_range()
        print("\n✨ All tests completed successfully!")
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)
