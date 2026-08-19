#!/usr/bin/env python3
"""
示例：展示与 Go 实现完全一致的 OpenRouter GPT-5 请求格式
"""

import json
import requests
import os
from typing import Dict, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def make_gpt5_openrouter_request(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    reasoning_effort: str = "low"
) -> Dict[str, Any]:
    """
    按照 Go 实现的精确格式发起 GPT-5 请求
    
    对应 Go 代码中的 GPT5OpenRouterRequest 结构
    """
    
    # 构建消息（与 Go 实现一致）
    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user", 
            "content": user_prompt
        }
    ]
    
    # 构建 web search 工具配置（对应 Go 的 GPT5OpenRouterWebSearchTool）
    web_search_tool = {
        "type": "web_search",
        "search_context_size": "medium",
        "user_location": {
            "type": "approximate",
            "country": "US"
        }
    }
    
    # 构建含 OpenRouter 专属参数的请求体（对应 Go 的 GPT5OpenRouterRequest）
    request_body = {
        "model": "openai/gpt-5.6-sol",  # Go 代码中的默认值
        "messages": messages,
        "tools": [web_search_tool],
        "tool_choice": "auto",
        "parallel_tool_calls": True,
        "reasoning": {
            "effort": reasoning_effort,
            "generate_summary": False
        },
        "background": False,
        "stream": False  # 流式时可改为 True
    }
    
    print("="*60)
    print("GPT-5 OpenRouter Request (matching Go implementation):")
    print("="*60)
    print(json.dumps(request_body, indent=2))
    print("="*60)
    
    # 设置请求头（与 Go 实现一致）
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # 发起请求
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    try:
        response = requests.post(
            url,
            headers=headers,
            json=request_body,
            timeout=600  # 与 Go 的超时一致
        )
        
        print(f"\nResponse Status: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            
            # 记录 token 用量（与 Go 的日志一致）
            if "usage" in response_data:
                usage = response_data["usage"]
                input_tokens = usage.get(
                    "prompt_tokens", usage.get("input_tokens", 0)
                )
                output_tokens = usage.get(
                    "completion_tokens", usage.get("output_tokens", 0)
                )
                input_details = usage.get(
                    "prompt_tokens_details", usage.get("input_tokens_details")
                )
                output_details = usage.get(
                    "completion_tokens_details", usage.get("output_tokens_details")
                )
                print("\nGPT-5 OpenRouter Usage:")
                print(f"  Input: {input_tokens} tokens", end="")
                if isinstance(input_details, dict):
                    print(f" (cached: {input_details.get('cached_tokens', 0)})")
                else:
                    print()
                    
                print(f"  Output: {output_tokens} tokens", end="")
                if isinstance(output_details, dict):
                    print(f" (reasoning: {output_details.get('reasoning_tokens', 0)})")
                else:
                    print()
                    
                print(f"  Total: {usage.get('total_tokens', 0)}")
            
            return response_data
        else:
            print(f"\nError: {response.text}")
            return {"error": response.text, "status_code": response.status_code}
            
    except Exception as e:
        print(f"\nException: {str(e)}")
        return {"error": str(e)}


def demonstrate_streaming_response():
    """
    演示流式响应的处理方式（对应 Go 的 handleStreamingResponse）
    """
    print("\n" + "="*60)
    print("Streaming Response Handler (pseudo-code matching Go):")
    print("="*60)
    
    streaming_code = '''
def handle_streaming_response(response):
    """
    Handle streaming responses from GPT-5 OpenRouter API
    Matches Go handleStreamingResponse function
    """
    content_builder = []
    reasoning_builder = []
    reasoning_token_count = 0
    
    for line in response.iter_lines():
        if not line:
            continue
            
        line_str = line.decode('utf-8')
        
        if not line_str.startswith("data: "):
            continue
            
        data = line_str[6:]  # Remove "data: " prefix
        
        if data == "[DONE]":
            break
            
        try:
            chunk = json.loads(data)
            
            if "choices" in chunk and len(chunk["choices"]) > 0:
                delta = chunk["choices"][0].get("delta", {})
                
                # Check for reasoning content
                if "reasoning_content" in delta:
                    reasoning = delta["reasoning_content"]
                    reasoning_builder.append(reasoning)
                    reasoning_token_count += 1
                    print(f"🧠 [GPT-5 THINKING] {reasoning}")
                
                # Check for regular content
                if "content" in delta:
                    content = delta["content"]
                    content_builder.append(content)
                    
        except json.JSONDecodeError:
            continue
    
    final_content = "".join(content_builder)
    return final_content
'''
    print(streaming_code)


def main():
    """
    主演示流程
    """
    print("\n" + "="*60)
    print("   GPT-5 OpenRouter Request Format Demo")
    print("   Exact match with Go implementation")
    print("="*60)
    
    # 从环境变量读取 API Key
    api_key = os.getenv("OPENROUTER_API_KEY")
    
    if not api_key:
        print("\n❌ Error: OPENROUTER_API_KEY not found in environment")
        print("Please set: export OPENROUTER_API_KEY=your-openrouter-api-key")
        return
    
    # 示例提示词
    system_prompt = "You are a helpful AI assistant with web search capabilities."
    user_prompt = "What are the latest developments in artificial intelligence?"
    
    print("\n1. Making request with LOW reasoning effort:")
    print("-"*60)
    result_low = make_gpt5_openrouter_request(
        api_key=api_key,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        reasoning_effort="low"
    )
    
    if "choices" in result_low:
        content = result_low["choices"][0]["message"]["content"]
        print(f"\nResponse preview: {content[:200]}...")
    
    print("\n2. Making request with HIGH reasoning effort:")
    print("-"*60)
    result_high = make_gpt5_openrouter_request(
        api_key=api_key,
        system_prompt=system_prompt,
        user_prompt="Explain the implications of quantum computing on cryptography",
        reasoning_effort="high"
    )
    
    if "choices" in result_high:
        content = result_high["choices"][0]["message"]["content"]
        print(f"\nResponse preview: {content[:200]}...")
    
    # 展示流式处理器
    demonstrate_streaming_response()
    
    print("\n" + "="*60)
    print("Demo complete! This shows the exact request format from Go.")
    print("="*60)


if __name__ == "__main__":
    main()
