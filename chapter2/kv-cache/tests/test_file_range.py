#!/usr/bin/env python3
"""
read_file 工具 offset 与 size 参数的测试脚本
"""

from agent import LocalFileTools

def test_file_range_reading():
    """测试用 offset 和 size 参数读文件"""
    
    print("🧪 Testing File Range Reading")
    print("="*60)
    
    # 初始化工具
    tools = LocalFileTools(root_dir="../..")
    
    # 测试文件
    test_file = "chapter1/context/agent.py"
    
    # 测试 1：读前 10 行
    print("\n1️⃣ Reading first 10 lines:")
    result = tools.read_file(test_file, offset=0, size=10)
    if result["success"]:
        print(f"   ✓ Read {result['lines_read']} lines from total {result['total_lines']}")
        print(f"   Range: lines {result['offset']}-{result['end_line']}")
        print(f"   First line: {result['content'].split(chr(10))[0][:50]}...")
    else:
        print(f"   ✗ Error: {result['error']}")
    
    # 测试 2：读 100-110 行
    print("\n2️⃣ Reading lines 100-110:")
    result = tools.read_file(test_file, offset=100, size=10)
    if result["success"]:
        print(f"   ✓ Read {result['lines_read']} lines")
        print(f"   Range: lines {result['offset']}-{result['end_line']}")
        lines = result['content'].split('\n')
        if lines:
            print(f"   Sample: {lines[0][:60]}...")
    else:
        print(f"   ✗ Error: {result['error']}")
    
    # 测试 3：从 offset 250 读 size 500（按指定）
    print("\n3️⃣ Reading from offset 250, size 500:")
    result = tools.read_file(test_file, offset=250, size=500)
    if result["success"]:
        print(f"   ✓ Read {result['lines_read']} lines")
        print(f"   Range: lines {result['offset']}-{result['end_line']}")
        print(f"   Total file has {result['total_lines']} lines")
    else:
        print(f"   ✗ Error: {result['error']}")
    
    # 测试 4：不指定 size（从 offset 读到末尾）
    print("\n4️⃣ Reading from offset 700 to end:")
    result = tools.read_file(test_file, offset=700)
    if result["success"]:
        print(f"   ✓ Read {result['lines_read']} lines")
        print(f"   Range: lines {result['offset']}-{result['end_line']}")
    else:
        print(f"   ✗ Error: {result['error']}")
    
    # 测试 5：offset 超出文件长度
    print("\n5️⃣ Testing offset beyond file length:")
    result = tools.read_file(test_file, offset=10000, size=10)
    if result["success"]:
        print(f"   ✓ Handled gracefully: {result.get('message', 'No error')}")
        print(f"   Lines read: {result['lines_read']}")
    else:
        print(f"   Result: {result}")
    
    # 测试 6：读整个文件（不指定 offset 和 size）
    print("\n6️⃣ Reading entire file (default behavior):")
    result = tools.read_file("chapter1/context/README.md")
    if result["success"]:
        print(f"   ✓ Read entire file")
        print(f"   Total lines: {result['total_lines']}")
        print(f"   Lines read: {result['lines_read']}")
        print(f"   Truncated: {result.get('truncated', False)}")
    else:
        print(f"   ✗ Error: {result['error']}")
    
    # 测试 7：API 风格用法（offset=250, size=500）
    print("\n7️⃣ API-style usage (offset=250, size=500):")
    result = tools.read_file("chapter2/local_llm_serving/main.py", offset=250, size=500)
    if result["success"]:
        print(f"   ✓ Successfully read lines {result['offset']}-{result['end_line']}")
        print(f"   Lines read: {result['lines_read']}")
        print(f"   File has {result['total_lines']} total lines")
        
        # 展示部分内容
        lines = result['content'].split('\n')[:3]
        print("\n   First 3 lines of content:")
        for i, line in enumerate(lines):
            print(f"     Line {250+i}: {line[:60]}..." if len(line) > 60 else f"     Line {250+i}: {line}")
    
    print("\n" + "="*60)
    print("✅ File range reading tests complete!")
    print("\nThe read_file tool now supports:")
    print("  • offset: Starting line number (0-based)")
    print("  • size: Number of lines to read")
    print("  • Handles edge cases gracefully")
    print("  • Maintains security boundaries")

if __name__ == "__main__":
    test_file_range_reading()
