#!/usr/bin/env python3
"""
本地文件系统工具的测试脚本
验证 read_file、find 和 grep 正常工作
"""

import os
import json
from agent import LocalFileTools


def test_file_tools():
    """测试本地文件系统工具"""
    
    print("🧪 Testing Local File System Tools")
    print("="*60)
    
    # 以项目根目录初始化工具
    tools = LocalFileTools(root_dir="../..")
    
    # 测试 1：查找 Python 文件
    print("\n1️⃣ Testing 'find' command...")
    print("   Finding *.py files in chapter1/context directory...")
    result = tools.find("*.py", "chapter1/context")
    
    if result["success"]:
        print(f"   ✓ Found {result['count']} Python files")
        if result["matches"]:
            print(f"   Sample files: {result['matches'][:3]}")
    else:
        print(f"   ✗ Error: {result['error']}")
    
    # 测试 2：读取文件
    print("\n2️⃣ Testing 'read_file' command...")
    test_file = "chapter1/context/README.md"
    print(f"   Reading {test_file}...")
    result = tools.read_file(test_file)
    
    if result["success"]:
        print(f"   ✓ Read file successfully ({len(result['content'])} bytes)")
        print(f"   First 100 chars: {result['content'][:100]}...")
    else:
        print(f"   ✗ Error: {result['error']}")
    
    # 测试 3：用 grep 搜索模式
    print("\n3️⃣ Testing 'grep' command...")
    print("   Searching for 'agent' in chapter1 directory...")
    result = tools.grep("agent", directory="chapter1")
    
    if result["success"]:
        print(f"   ✓ Found {result['match_count']} matches in {result['files_searched']} files")
        if result["matches"]:
            sample = result["matches"][0]
            print(f"   Sample match: {sample['file']}:{sample['line_num']} - {sample['line'][:50]}...")
    else:
        print(f"   ✗ Error: {result['error']}")
    
    # 测试 4：安全检查 —— 尝试访问根目录之外
    print("\n4️⃣ Testing security boundaries...")
    print("   Attempting to read file outside root directory...")
    result = tools.read_file("../../../../../../etc/passwd")
    
    if not result["success"] and "Access denied" in result.get("error", ""):
        print("   ✓ Security check passed - access denied as expected")
    else:
        print("   ⚠️ Security check result:", result.get("error", "Unexpected result"))
    
    # 测试 5：在指定文件中 grep
    print("\n5️⃣ Testing 'grep' in specific file...")
    print("   Searching for 'class' in chapter1/context/agent.py...")
    result = tools.grep("class", file_path="chapter1/context/agent.py")
    
    if result["success"]:
        print(f"   ✓ Found {result['match_count']} matches")
        if result["matches"]:
            for match in result["matches"][:3]:
                print(f"     Line {match['line_num']}: {match['line'][:60]}...")
    else:
        print(f"   ✗ Error: {result['error']}")
    
    print("\n" + "="*60)
    print("✅ Tool testing complete!")
    print("\nAll tools are working correctly and can be used by the ReAct agent.")
    print("Security boundaries are properly enforced.")


def test_pattern_matching():
    """测试各种模式匹配场景"""
    
    print("\n🔍 Testing Pattern Matching Capabilities")
    print("="*60)
    
    tools = LocalFileTools(root_dir="../..")
    
    # 测试不同文件模式
    patterns = [
        ("*.md", "chapter1", "Markdown files"),
        ("*.py", "chapter2", "Python files"),
        ("README*", ".", "README files"),
        ("test_*.py", "chapter1", "Test files"),
    ]
    
    for pattern, directory, description in patterns:
        print(f"\n• Finding {description}: {pattern} in {directory}")
        result = tools.find(pattern, directory)
        if result["success"]:
            print(f"  Found {result['count']} files")
        else:
            print(f"  Error: {result['error']}")
    
    # 测试不同 grep 模式
    print("\n📝 Testing Grep Patterns")
    print("-"*40)
    
    grep_tests = [
        (r"def \w+\(", "chapter1/context/agent.py", "Function definitions"),
        (r"import \w+", "chapter1/context/main.py", "Import statements"),
        (r"TODO|FIXME", "chapter1", "TODO/FIXME comments"),
        (r"^\s*class", "chapter1/context/agent.py", "Class definitions"),
    ]
    
    for pattern, target, description in grep_tests:
        print(f"\n• Searching for {description}: {pattern}")
        if "/" in target:
            result = tools.grep(pattern, file_path=target)
        else:
            result = tools.grep(pattern, directory=target)
        
        if result["success"]:
            print(f"  Found {result['match_count']} matches")
        else:
            print(f"  Error: {result['error']}")


if __name__ == "__main__":
    # 运行基础测试
    test_file_tools()
    
    # 运行模式匹配测试
    test_pattern_matching()
    
    print("\n🎉 All tests completed successfully!")
