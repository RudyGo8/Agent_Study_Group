"""
Ollama 原生工具调用实现
使用 Ollama 标准工具调用 API（需要支持工具调用的模型）
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
import ollama
from tools import ToolRegistry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OllamaNativeAgent:
    """使用 Ollama 原生工具调用能力的 Agent"""
    
    def __init__(self, model: str = "qwen3:0.6b"):
        """
        用支持工具调用的模型初始化
        """
        self.model = model
        self.client = ollama.Client()
        self.tool_registry = ToolRegistry()
        self.conversation_history = []
        self._think_disabled: set[str] = set()
        
        # 检查 Ollama 是否在运行
        try:
            self.client.list()
            logger.info(f"✅ Connected to Ollama with model: {model}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Ollama: {e}")
            logger.info("Please start Ollama with: ollama serve")
    
    def _convert_tools_to_ollama_format(self) -> List[Dict]:
        """把工具注册表转换为 Ollama 要求的格式"""
        tools = []
        for tool_def in self.tool_registry.get_tool_schemas():
            # Ollama 使用的格式与 OpenAI 相同
            tools.append(tool_def)
        return tools
    
    def _chat_with_think_fallback(self, **kwargs) -> dict:
        """尽可能以 think=True 调用 client.chat，不支持时优雅回退。

        不支持思考的模型（qwen2.5、llama3.2、gemma 等）在 think=True 时
        返回 400 错误。此方法对每个模型只捕获一次该错误并去掉 think 重试，
        同时缓存结果，后续调用不再付出试错成本。对于意外错误（旧版客户端、
        未知问题）也会去掉 think 重试——若错误与 think 无关，重试会再次
        失败，异常自然向上抛出。
        """
        if self.model in self._think_disabled:
            return self.client.chat(**kwargs)

        try:
            return self.client.chat(think=True, **kwargs)
        except ollama.ResponseError as e:
            if e.status_code == 400:
                logger.info("Model '%s' does not support thinking, disabling", self.model)
                self._think_disabled.add(self.model)
                return self.client.chat(**kwargs)
            raise
        except Exception:
            # think=True 出现未知失败（旧版客户端、意外问题）。
            # 去掉 think 重试；若错误与之无关，重试会再次失败，
            # 异常自然向上抛出。
            logger.warning("think=True failed for '%s', retrying without think", self.model)
            self._think_disabled.add(self.model)
            return self.client.chat(**kwargs)

    def _execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[str]:
        """
        执行工具调用并按顺序返回结果。
        同一轮的多个工具调用并行执行（它们天然相互独立，
        因为模型是在未看到任何结果的情况下一次生成的）。
        """
        def run_one(tool_call: Dict[str, Any]) -> str:
            function = tool_call.get('function', {})
            tool_name = function.get('name')
            tool_args = function.get('arguments')
            
            # 参数若是字符串则先解析
            if isinstance(tool_args, str):
                try:
                    tool_args = json.loads(tool_args)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse tool arguments: {tool_args}")
                    tool_args = {}
            
            # 执行工具
            logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
            return self.tool_registry.execute_tool(tool_name, tool_args)
        
        if len(tool_calls) <= 1:
            return [run_one(tc) for tc in tool_calls]
        
        # 相互独立的工具调用并发执行；executor.map 保持顺序
        with ThreadPoolExecutor(max_workers=len(tool_calls)) as executor:
            return list(executor.map(run_one, tool_calls))
    
    def chat(self, message: str, use_tools: bool = True,  
             temperature: float = 0.3, stream: bool = False) -> str:
        """
        使用 Ollama 原生工具调用发送消息

        Args:
            message: 用户消息
            use_tools: 是否启用工具调用
            temperature: 采样温度
            stream: 是否流式返回响应

        Returns:
            模型的最终响应（流式模式下为生成器）
        """
        if stream:
            return self.chat_stream(message, use_tools, temperature)
        
        # 下面是原有的非流式实现...
        # 把用户消息加入历史
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        # 启用工具时先准备工具列表
        tools = self._convert_tools_to_ollama_format() if use_tools else None
        
        try:
            # 带工具调用 Ollama
            response = self._chat_with_think_fallback(
                model=self.model,
                messages=self.conversation_history,
                tools=tools,
                options={"temperature": temperature},
            )
            
            # 检查模型是否发起工具调用
            message_content = response.get('message', {})
            
            # 若有工具调用则处理
            if 'tool_calls' in message_content:
                tool_calls = message_content['tool_calls']
                logger.info(f"Model requested {len(tool_calls)} tool call(s)")
                
                # 把带工具调用的 assistant 消息加入历史
                self.conversation_history.append({
                    "role": "assistant",
                    "content": message_content.get('content', ''),
                    "tool_calls": tool_calls
                })
                
                # 执行工具调用（相互独立的调用并行执行）
                results = self._execute_tool_calls(tool_calls)
                
                # 把工具结果加入对话
                for result in results:
                    self.conversation_history.append({
                        "role": "tool",
                        "content": result
                    })
                
                # 带工具结果获取最终响应（仍要传入 tools！）
                final_response = self._chat_with_think_fallback(
                    model=self.model,
                    messages=self.conversation_history,
                    tools=tools,  # 重要：保持 tools 可用
                    options={"temperature": temperature},
                )
                
                final_content = final_response.get('message', {}).get('content', '')
                
                # 清理响应（去掉可能存在的 <think> 标签）
                import re
                final_content = re.sub(r'<think>.*?</think>', '', final_content, flags=re.DOTALL).strip()
                
                # 把最终响应加入历史
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_content
                })
                
                return final_content
            
            else:
                # 没有工具调用，直接返回响应
                content = message_content.get('content', '')
                self.conversation_history.append({
                    "role": "assistant",
                    "content": content
                })
                return content
                
        except Exception as e:
            logger.error(f"Error in chat: {e}")
            return f"Error: {e}"
    
    def chat_stream(self, message: str, use_tools: bool = True,
                    temperature: float = 0.3):
        """
        流式发送消息给模型，并在 ReAct 循环中处理工具调用

        逐个 yield 分片，包含：
        - type: 'thinking'、'tool_call'、'tool_result'、'content'
        - content: 实际内容
        """
        # 把用户消息加入历史
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        # 启用工具时先准备工具列表
        tools = self._convert_tools_to_ollama_format() if use_tools else None
        
        # ReAct 循环——持续迭代直到不再需要工具调用
        max_iterations = 10  # 防止无限循环
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            
            try:
                # 获取模型响应
                stream_response = self._chat_with_think_fallback(
                    model=self.model,
                    messages=self.conversation_history,
                    tools=tools,
                    options={"temperature": temperature},
                    stream=True,
                )
                
                collected_content = []
                tool_calls_detected = False
                pending_tool_calls = []
                thinking_buffer = ""
                in_thinking = False
                
                # 处理流式响应
                for chunk in stream_response:
                    # 从分片中提取消息内容
                    message_chunk = chunk.get('message', {})
                    thinking_chunk = message_chunk.get('thinking', '')
                    content_chunk = message_chunk.get('content', '')
                    
                    if thinking_chunk:
                        yield {"type": "thinking", "content": thinking_chunk}
                    
                    if content_chunk:
                        collected_content.append(content_chunk)
                        
                        # 处理思考内容
                        if '<think>' in content_chunk:
                            in_thinking = True
                            thinking_buffer = content_chunk
                            # 提取 <think> 之前的内容
                            import re
                            before_think = content_chunk.split('<think>')[0]
                            if before_think:
                                yield {"type": "content", "content": before_think}
                            # 提取该分片中的思考内容
                            if '</think>' in content_chunk:
                                # 一个分片内包含完整思考
                                thinking_match = re.search(r'<think>(.*?)</think>', content_chunk, re.DOTALL)
                                if thinking_match:
                                    thinking_content = thinking_match.group(1).strip()
                                    # 逐字符流式输出思考内容
                                    for char in thinking_content:
                                        yield {"type": "thinking", "content": char}
                                # 检查 </think> 之后的内容
                                after_think = content_chunk.split('</think>')[-1]
                                if after_think:
                                    yield {"type": "content", "content": after_think}
                                in_thinking = False
                                thinking_buffer = ""
                            else:
                                # 思考未结束，先输出已收到的部分
                                partial_thinking = content_chunk.split('<think>')[-1]
                                for char in partial_thinking:
                                    yield {"type": "thinking", "content": char}
                        elif in_thinking:
                            thinking_buffer += content_chunk
                            if '</think>' in content_chunk:
                                # 思考结束
                                before_end = content_chunk.split('</think>')[0]
                                for char in before_end:
                                    yield {"type": "thinking", "content": char}
                                # 检查 </think> 之后的内容
                                after_think = content_chunk.split('</think>')[-1]
                                if after_think:
                                    yield {"type": "content", "content": after_think}
                                in_thinking = False
                                thinking_buffer = ""
                            else:
                                # 继续流式输出思考内容
                                for char in content_chunk:
                                    yield {"type": "thinking", "content": char}
                        else:
                            # 普通正文——原样 yield
                            yield {"type": "content", "content": content_chunk}
                    
                    # 检查分片中是否有工具调用
                    if 'tool_calls' in message_chunk:
                        tool_calls_detected = True
                        
                        for tool_call in message_chunk['tool_calls']:
                            function = tool_call.get('function', {})
                            tool_name = function.get('name')
                            tool_args = function.get('arguments')
                            
                            # 参数若是字符串则先解析
                            if isinstance(tool_args, str):
                                try:
                                    tool_args = json.loads(tool_args)
                                except json.JSONDecodeError:
                                    tool_args = {}
                            
                            # 先收集工具调用，流结束后再执行，
                            # 以便多个调用可以并行。
                            # 跳过重复项：某些服务端会在每个分片里
                            # 流式返回累积的 tool_calls 列表。
                            if not any(
                                tc.get('function', {}).get('name') == tool_name
                                and tc.get('function', {}).get('arguments') == function.get('arguments')
                                for tc in pending_tool_calls
                            ):
                                pending_tool_calls.append(tool_call)
                                yield {"type": "tool_call", "content": {"name": tool_name, "arguments": tool_args}}
                
                # 并行执行本轮所有工具调用
                if pending_tool_calls:
                    results = self._execute_tool_calls(pending_tool_calls)
                    for result in results:
                        # 输出工具结果
                        yield {"type": "tool_result", "content": result}
                        
                        # 把工具结果加入对话
                        self.conversation_history.append({
                            "role": "tool",
                            "content": result
                        })
                
                # 把完整响应存入历史
                complete_response = ''.join(collected_content)
                
                if tool_calls_detected:
                    # 把 assistant 消息加入历史
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": complete_response if complete_response else ""
                    })
                    # 继续 ReAct 循环——让模型决定下一步
                    # 循环会继续并获取下一个响应
                else:
                    # 没有工具调用——已得到最终响应
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": complete_response
                    })
                    # 退出 ReAct 循环
                    break
                    
            except Exception as e:
                logger.error(f"Error in chat stream: {e}")
                yield {"type": "error", "content": str(e)}
                break
        
        # 检查是否达到最大迭代次数
        if iteration >= max_iterations:
            yield {"type": "error", "content": "Maximum iterations reached in ReAct loop"}
    
    def reset_conversation(self):
        """清空对话历史"""
        self.conversation_history = []
        logger.info("Conversation history reset")


class OllamaOpenAICompatible:
    """通过 Ollama 的 OpenAI 兼容端点使用 Ollama"""
    
    def __init__(self, model: str = "qwen3:0.6b", 
                 base_url: str = "http://localhost:11434/v1"):
        """
        使用 Ollama 的 OpenAI 兼容 API 初始化

        这样对工具调用的兼容性更好
        """
        from openai import OpenAI
        
        self.model = model
        self.client = OpenAI(
            base_url=base_url,
            api_key="ollama"  # Ollama 不需要真实 key
        )
        self.tool_registry = ToolRegistry()
        self.conversation_history = []
        
        logger.info(f"✅ Initialized Ollama OpenAI-compatible client with {model}")
    
    def chat(self, message: str, use_tools: bool = True,
             temperature: float = 0.3) -> str:
        """
        通过 OpenAI 兼容端点聊天
        """
        # 加入用户消息
        self.conversation_history.append({
            "role": "user",
            "content": message
        })
        
        # 准备工具
        tools = self.tool_registry.get_tool_schemas() if use_tools else None
        
        try:
            # 带工具调用
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.conversation_history,
                tools=tools,
                tool_choice="auto" if tools else None,
                temperature=temperature
            )
            
            assistant_message = response.choices[0].message
            
            # 检查工具调用
            if assistant_message.tool_calls:
                logger.info(f"Model requested {len(assistant_message.tool_calls)} tool(s)")
                
                # 把 assistant 消息加入历史
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": tc.type,
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in assistant_message.tool_calls
                    ]
                })
                
                # 执行工具调用（相互独立的调用并行执行；
                # executor.map 保持顺序）
                def run_one(tool_call):
                    # 解析参数
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    
                    # 执行工具
                    return self.tool_registry.execute_tool(
                        tool_call.function.name,
                        args
                    )
                
                tool_calls_list = list(assistant_message.tool_calls)
                if len(tool_calls_list) <= 1:
                    results = [run_one(tc) for tc in tool_calls_list]
                else:
                    with ThreadPoolExecutor(max_workers=len(tool_calls_list)) as executor:
                        results = list(executor.map(run_one, tool_calls_list))
                
                # 加入工具结果
                for tool_call, result in zip(tool_calls_list, results):
                    self.conversation_history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })
                
                # 获取最终响应
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.conversation_history,
                    tools=tools,   # 重要：保持 tools 可用
                    temperature=temperature
                )
                
                final_content = final_response.choices[0].message.content
                
                # 加入历史
                self.conversation_history.append({
                    "role": "assistant",
                    "content": final_content
                })
                
                return final_content
            
            else:
                # 没有工具调用
                content = assistant_message.content
                self.conversation_history.append({
                    "role": "assistant",
                    "content": content
                })
                return content
                
        except Exception as e:
            logger.error(f"Error: {e}")
            return f"Error: {e}"
    
    def reset_conversation(self):
        """清空对话历史"""
        self.conversation_history = []
        logger.info("Conversation reset")


def test_native_tools():
    """测试 Ollama 原生工具调用"""
    print("="*60)
    print("🔧 Testing Ollama Native Tool Calling")
    print("="*60)
    
    # 用默认模型测试
    models_to_test = [
        "qwen3:0.6b",  # 本项目默认模型
    ]
    
    for model_name in models_to_test:
        print(f"\n📦 Testing with {model_name}")
        print("-"*40)
        
        try:
            # 检查模型是否可用
            client = ollama.Client()
            available_models = [m['name'] for m in client.list()['models']]
            
            if not any(model_name in m for m in available_models):
                print(f"⚠️  Model {model_name} not installed")
                print(f"   Install with: ollama pull {model_name}")
                continue
            
            # 测试该模型
            agent = OllamaNativeAgent(model=model_name)
            
            test_queries = [
                "What's 15 * 23?",
                "What's the weather in London?",
            ]
            
            for query in test_queries:
                print(f"\n👤 User: {query}")
                response = agent.chat(query)
                print(f"🤖 Assistant: {response[:200]}...")  # 截断过长的响应
                agent.reset_conversation()
                
        except Exception as e:
            print(f"❌ Error testing {model_name}: {e}")
    
    print("\n" + "="*60)
    print("💡 Note:")
    print("This project uses qwen3:0.6b as the default model.")
    print("Install with: ollama pull qwen3:0.6b")
    print("="*60)


def demo():
    """带完整工具调用的交互式演示"""
    print("="*60)
    print("🎯 Ollama Standard Tool Calling Demo")
    print("="*60)
    
    # 让用户选择实现方式
    print("\nChoose implementation:")
    print("1. Native Ollama API (recommended)")
    print("2. OpenAI-compatible API")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "2":
        print("\nUsing OpenAI-compatible endpoint...")
        agent = OllamaOpenAICompatible()
    else:
        print("\nUsing native Ollama API...")
        # 检查最合适的可用模型
        try:
            client = ollama.Client()
            models = [m['name'] for m in client.list()['models']]
            
            # 默认使用 qwen3:0.6b
            model = "qwen3:0.6b"
            
            if model in models:
                print(f"Using recommended model: {model}")
            else:
                print(f"Recommended model {model} not found")
                print("Install with: ollama pull qwen3:0.6b")
                # 回退到第一个可用模型
                model = models[0] if models else "qwen3:0.6b"
                print(f"Using fallback model: {model}")
                
            agent = OllamaNativeAgent(model=model)
            
        except Exception as e:
            print(f"Error: {e}")
            return
    
    # 交互循环
    print("\n💬 Chat with the assistant (type 'exit' to quit)")
    print("-"*40)
    
    while True:
        user_input = input("\n👤 You: ").strip()
        if user_input.lower() in ['exit', 'quit']:
            break
        
        response = agent.chat(user_input)
        print(f"🤖 Assistant: {response}")
    
    print("\n👋 Goodbye!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_native_tools()
    else:
        demo()
