"""
提示工程实验的消融工具函数
"""

import random
import re
from enum import Enum
from typing import List, Dict, Any, Optional
import copy


class ToneStyle(Enum):
    """Agent 的不同语气风格"""
    DEFAULT = "default"
    TRUMP = "trump"
    CASUAL = "casual"


# 语气风格指令
TONE_INSTRUCTIONS = {
    ToneStyle.TRUMP: """
You must communicate in the distinctive style of Donald Trump. This means:
- Use superlatives frequently ("tremendous", "fantastic", "the best", "incredible", "nobody does it better")
- Speak with absolute confidence and make bold claims
- Use repetition for emphasis ("very, very important", "believe me")
- Reference your success and expertise often
- Use simple, direct language with short, punchy sentences
- Show enthusiasm with phrases like "It's going to be great!" or "You're going to love it!"
- Occasionally use "folks" when addressing users
- Be assertive and decisive in your statements
- Use "frankly" and "honestly" to emphasize points
- Make everything sound like a big deal

Example responses:
- Instead of "I'll help you book a flight", say "I'm going to get you the best flight deal ever, believe me. Nobody books flights better than me."
- Instead of "There's an error", say "This is a disaster, frankly. But don't worry, I'll fix it. I always fix things. It'll be tremendous."
""",
    
    ToneStyle.CASUAL: """
Speak with the user in a super casual, fun, and cool tone. Use a ton of emojis, as well as slang and idioms. Be like their fun friend who's helping them out! 

Guidelines:
- Use lots of emojis throughout your responses 🎉✨😊🚀
- Use casual language and slang (e.g., "totally", "awesome", "no worries", "gotcha", "my bad")
- Be enthusiastic and upbeat
- Use informal greetings like "Hey there!", "What's up?", "Yo!"
- Use phrases like "Let's do this!", "You got it!", "Boom!", "Sweet!"
- Keep things light and friendly
- Use idioms and expressions like "piece of cake", "no sweat", "you're all set"
- Add personality with expressions like "Oops!", "Yay!", "Woohoo!"

Example responses:
- Instead of "I'll help you book a flight", say "Hey! Let's get you that flight booked! 🛫✨ This is gonna be awesome!"
- Instead of "There's an error", say "Oops! 😅 Looks like we hit a little snag, but no worries! Let me fix that for you real quick! 💪"
""",
    
    ToneStyle.DEFAULT: ""  # default 不做任何修改
}


def apply_tone_modification(text: str, tone_style: ToneStyle) -> str:
    """
    对文本（wiki 或系统提示词）应用语气修改

    参数:
        text: 原始文本
        tone_style: 要应用的语气风格

    返回:
        在开头拼接了语气指令的文本
    """
    if tone_style == ToneStyle.DEFAULT:
        return text
    
    tone_instruction = TONE_INSTRUCTIONS[tone_style]
    
    # 把语气指令加到文本开头
    if text:
        return f"{tone_instruction}\n\n---ORIGINAL INSTRUCTIONS---\n\n{text}"
    else:
        return tone_instruction


def load_randomized_wiki(env: str) -> str:
    """
    加载指定环境预先生成的随机化 wiki

    参数:
        env: 环境名（'airline' 或 'retail'）

    返回:
        预先随机化好的 wiki 文本
    """
    import os
    from pathlib import Path
    
    # 取本脚本所在目录
    script_dir = Path(__file__).parent
    
    if env == "airline":
        wiki_path = script_dir / "wiki_airline_randomized.md"
    elif env == "retail":
        wiki_path = script_dir / "wiki_retail_randomized.md"
    else:
        raise ValueError(f"Unknown environment: {env}")
    
    if not wiki_path.exists():
        raise FileNotFoundError(f"Randomized wiki not found: {wiki_path}")
    
    with open(wiki_path, 'r') as f:
        return f.read()


def remove_descriptions_recursive(obj: Any) -> Any:
    """
    递归移除嵌套对象中的所有 description 字段

    参数:
        obj: 待处理对象

    返回:
        移除全部 description 后的对象
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == "description":
                # 把 description 置为空字符串以达到移除效果
                result[key] = ""
            else:
                # 递归处理嵌套结构
                result[key] = remove_descriptions_recursive(value)
        return result
    elif isinstance(obj, list):
        # 逐项处理列表
        return [remove_descriptions_recursive(item) for item in obj]
    else:
        # 原始值原样返回
        return obj


def remove_tool_descriptions(tools_info: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    移除工具及其参数（含嵌套结构）的描述

    参数:
        tools_info: 原始工具信息

    返回:
        移除全部描述后的工具信息
    """
    modified_tools = []

    for tool in tools_info:
        # 深拷贝，避免改动原始对象
        modified_tool = copy.deepcopy(tool)

        # 递归移除所有 description
        modified_tool = remove_descriptions_recursive(modified_tool)
        
        modified_tools.append(modified_tool)
    
    return modified_tools
