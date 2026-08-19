#!/usr/bin/env python3
"""
交互式模式选择的测试脚本
"""

from main import select_mode_interactive

def test_mode_selection(monkeypatch):
    """不实际运行 Agent，仅测试交互式模式选择"""
    
    print("🧪 Testing Interactive Mode Selection")
    print("(This is a test - no agent will actually run)")
    
    # 测试选择菜单
    monkeypatch.setattr("builtins.input", lambda _prompt: "7")
    selected = select_mode_interactive()
    assert selected == "compare"
    
    print("\n" + "="*60)
    if selected == "compare":
        print("✅ You selected: Compare all modes")
        print("In real usage, this would run all 6 implementations and compare them.")
    else:
        print(f"✅ You selected: {selected}")
        print(f"In real usage, this would run the '{selected}' implementation.")
    
    print("\nTest complete!")

if __name__ == "__main__":
    test_mode_selection()
