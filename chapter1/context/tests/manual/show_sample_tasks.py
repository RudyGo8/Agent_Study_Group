#!/usr/bin/env python3
"""
展示含 PDF 功能的示例任务的演示脚本
"""

import os
import sys
from pathlib import Path

from _bootstrap import add_project_root

add_project_root()

from main import get_sample_tasks, ensure_sample_pdfs

def main():
    """演示示例任务"""
    print("\n" + "="*60)
    print("🎯 CONTEXT-AWARE AGENT - SAMPLE TASKS DEMO")
    print("="*60)
    
    # 确保样例 PDF 存在
    print("\n📄 Checking for sample PDFs...")
    if ensure_sample_pdfs():
        print("✅ Sample PDFs are ready!")
    else:
        print("⚠️ Could not create sample PDFs, will use online alternatives")

    # 获取示例任务
    tasks = get_sample_tasks()
    
    print(f"\n📋 Found {len(tasks)} sample tasks:")
    print("-"*60)
    
    for i, task in enumerate(tasks, 1):
        print(f"\n{i}. {task['name']}")
        print(f"   📝 {task['description']}")
        print(f"   📊 Complexity: {'⭐' * (i if i <= 3 else 3)}")
        
        # 展示任务内容预览
        task_preview = task['task'].replace('\n', ' ')[:100] + "..."
        print(f"   💬 Preview: {task_preview}")
    
    print("\n" + "="*60)
    print("💡 USAGE TIPS:")
    print("-"*60)
    print("1. Run 'python main.py' to enter interactive mode")
    print("2. Type 'sample 2' to test PDF parsing capabilities")
    print("3. Type 'sample 5' for the most comprehensive test")
    print("4. Switch modes with 'mode no_reasoning' to see ablation effects")
    
    print("\n" + "="*60)
    print("🔬 ABLATION TESTING:")
    print("-"*60)
    print("Try running the same task in different modes:")
    print("  • full         - Everything works perfectly")
    print("  • no_history   - Agent forgets what it did")
    print("  • no_reasoning - No planning, chaotic execution")
    print("  • no_tool_calls - Can't do anything!")
    print("  • no_tool_results - Works blind, gets confused")
    
    print("\n" + "="*60)
    print("📊 PDF TASKS:")
    print("-"*60)
    
    # 检查本地 PDF 是否存在
    pdf_dir = Path("fixtures/pdfs")
    if pdf_dir.exists():
        pdfs = list(pdf_dir.glob("*.pdf"))
        if pdfs:
            print(f"✅ Found {len(pdfs)} local PDF files:")
            for pdf in pdfs:
                print(f"   • {pdf.name}")
            print("\nTask #2 will use these local PDFs for testing.")
        else:
            print("⚠️ No PDFs found in fixtures/pdfs/")
    else:
        print("📥 PDF directory not found. Run 'create_pdfs' command to generate samples.")
    
    print("\n" + "="*60)
    print("Ready to test! Run 'python main.py' to start.")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
