#!/usr/bin/env python
"""
查看已保存轨迹文件的小工具
用法: python view_trajectory.py [trajectory_file]
"""

import json
import sys
from pathlib import Path
from datetime import datetime

def format_time(iso_string):
    """把 ISO 时间戳转换为易读格式"""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso_string

def view_trajectory(file_path="trajectory.json"):
    """查看轨迹文件并格式化输出"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        print("\n" + "="*80)
        print("TRAJECTORY ANALYSIS")
        print("="*80)
        
        print(f"\n📅 Timestamp: {format_time(data['timestamp'])}")
        print(f"🤖 Model: {data['model']}")
        print(f"🔄 Total Iterations: {data['iteration']}")
        print(f"💬 Conversation Messages: {len(data['conversation_history'])}")
        print(f"🔧 Tool Calls: {len(data['tool_calls'])}")
        
        if data['final_answer']:
            print(f"\n✅ Task Completed Successfully")
            print(f"Final Answer Preview: {data['final_answer'][:200]}...")
        else:
            print(f"\n⚠️ Task Not Completed")
        
        # 展示工具调用分布
        if data['tool_calls']:
            print("\n📊 Tool Usage Summary:")
            tool_counts = {}
            for call in data['tool_calls']:
                name = call['tool_name']
                tool_counts[name] = tool_counts.get(name, 0) + 1
            
            for tool, count in tool_counts.items():
                print(f"  - {tool}: {count} call(s)")
        
        # 若存在则展示 TODO 列表
        if data['todo_list']:
            print("\n📋 TODO List:")
            for item in data['todo_list']:
                status_symbol = {
                    'pending': '⏳',
                    'in_progress': '🔄', 
                    'completed': '✅',
                    'cancelled': '❌'
                }.get(item['status'], '❓')
                print(f"  [{item['id']}] {status_symbol} {item['content']}")
        
        # 展示对话片段
        print("\n💬 Conversation Highlights:")
        for i, msg in enumerate(data['conversation_history'][:5], 1):
            role = msg['role']
            content = msg.get('content', '')
            if content:
                preview = content[:100].replace('\n', ' ')
                if len(content) > 100:
                    preview += "..."
                print(f"  {i}. [{role}] {preview}")
        
        if len(data['conversation_history']) > 5:
            print(f"  ... and {len(data['conversation_history']) - 5} more messages")
        
        print("\n" + "="*80)
        print(f"Full trajectory saved in: {file_path}")
        print(f"File size: {Path(file_path).stat().st_size:,} bytes")
        print("="*80 + "\n")
        
    except FileNotFoundError:
        print(f"❌ Error: Trajectory file '{file_path}' not found")
        print("Run an agent task first to generate a trajectory file.")
    except json.JSONDecodeError:
        print(f"❌ Error: Invalid JSON in '{file_path}'")
    except Exception as e:
        print(f"❌ Error reading trajectory: {e}")

if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else "trajectory.json"
    view_trajectory(file_path)
