"""
vLLM 工具调用 Agent 实现
演示如何基于 vLLM + Qwen3 实现工具调用
"""

import json
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple
from openai import OpenAI
from tools import ToolRegistry
from config import OPENAI_API_BASE, OPENAI_API_KEY, LOG_LEVEL

# 配置日志
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


class VLLMToolAgent:
    """基于 vLLM + Qwen3 模型实现工具调用的 Agent"""
    
    def __init__(self, api_base: str = OPENAI_API_BASE, api_key: str = OPENAI_API_KEY):
        """
        初始化 Agent 并连接 vLLM 服务端
        
        Args:
            api_base: vLLM 服务端地址
            api_key: API key（vLLM 不校验，填 "EMPTY" 即可）
        """
        self.client = OpenAI(
            api_key=api_key,
            base_url=api_base
        )
        self.tool_registry = ToolRegistry()
        self.conversation_history = []
        logger.info(f"Initialized VLLMToolAgent with server at {api_base}")
    
    def _format_system_prompt_with_tools(self) -> str:
        """
        按 Qwen3 格式生成带工具定义的系统提示词
        """
        tools_json = json.dumps(self.tool_registry.get_tool_schemas(), indent=2)
        
        system_prompt = f"""# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{tools_json}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{{"name": <function-name>, "arguments": <args-json-object>}}
</tool_call>

You are a helpful assistant that can use tools to answer questions and perform tasks.
When you need to use a tool, generate the appropriate tool call.
After receiving tool results, use them to provide a comprehensive answer to the user."""
        
        return system_prompt
    
    def _parse_tool_calls(self, content: str) -> List[Dict[str, Any]]:
        """
        从模型输出中解析工具调用
        提取 <tool_call> 标签之间的内容
        """
        tool_calls = []
        
        # 找出全部工具调用块
        import re
        pattern = r'<tool_call>(.*?)</tool_call>'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            try:
                tool_call = json.loads(match.strip())
                if "name" in tool_call and "arguments" in tool_call:
                    tool_calls.append({
                        "id": str(uuid.uuid4())[:8],  # 生成短 ID
                        "type": "function",
                        "function": {
                            "name": tool_call["name"],
                            "arguments": tool_call["arguments"]
                        }
                    })
                    logger.debug(f"Parsed tool call: {tool_call['name']}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool call JSON: {e}")
                logger.debug(f"Content was: {match}")
        
        return tool_calls
    
    def _execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        执行工具调用并返回结果。
        同一轮的多个工具调用并行执行（它们天然相互独立，
        因为模型是在未看到任何结果的情况下一次生成的）。同时保证
        失败工具的错误信息被正确格式化。
        """
        def run_one(tool_call: Dict[str, Any]) -> Dict[str, Any]:
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"]["arguments"]
            tool_id = tool_call["id"]
            
            logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
            
            # 执行工具
            result = self.tool_registry.execute_tool(tool_name, tool_args)
            
            # 检查结果是否表示出错
            try:
                result_dict = json.loads(result) if isinstance(result, str) else result
                if isinstance(result_dict, dict) and not result_dict.get("success", True):
                    # 工具执行失败——把错误信息格式化清楚
                    error_msg = f"❌ Tool '{tool_name}' execution failed:\n"
                    if "error" in result_dict:
                        error_msg += f"Error: {result_dict['error']}\n"
                    if "error_type" in result_dict:
                        error_msg += f"Type: {result_dict['error_type']}\n"
                    if "traceback" in result_dict:
                        error_msg += f"Traceback:\n{result_dict['traceback']}\n"
                    
                    logger.error(f"Tool {tool_name} failed: {result_dict.get('error', 'Unknown error')}")
                    result = error_msg
                else:
                    logger.debug(f"Tool {tool_name} returned: {result}")
            except (json.JSONDecodeError, TypeError):
                # 结果不是 JSON，原样透传
                logger.debug(f"Tool {tool_name} returned: {result}")
            
            # 格式化结果
            return {
                "role": "tool",
                "tool_call_id": tool_id,
                "name": tool_name,
                "content": result if isinstance(result, str) else str(result)
            }
        
        if len(tool_calls) <= 1:
            return [run_one(tc) for tc in tool_calls]
        
        # 相互独立的工具调用并发执行；executor.map 保持顺序
        with ThreadPoolExecutor(max_workers=len(tool_calls)) as executor:
            return list(executor.map(run_one, tool_calls))
    
    def _execute_single_tool(self, tool_data: Dict[str, Any]) -> Tuple[str, bool]:
        """
        执行一条已解析的工具调用（{"name": ..., "arguments": ...}）。
        返回 (result_text, is_error)，错误信息会被清晰格式化。
        """
        tool_name = tool_data["name"]
        try:
            result = self.tool_registry.execute_tool(tool_name, tool_data["arguments"])
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return f"❌ Tool execution exception: {str(e)}", True
        
        # 检查结果是否表示出错
        try:
            result_dict = json.loads(result) if isinstance(result, str) else result
            if isinstance(result_dict, dict) and not result_dict.get("success", True):
                # 工具执行失败——把错误信息格式化清楚
                error_msg = f"❌ Tool '{tool_name}' execution failed:\n"
                if "error" in result_dict:
                    error_msg += f"Error: {result_dict['error']}\n"
                if "error_type" in result_dict:
                    error_msg += f"Type: {result_dict['error_type']}\n"
                if "traceback" in result_dict:
                    error_msg += f"Traceback:\n{result_dict['traceback']}\n"
                
                logger.error(f"Tool {tool_name} failed: {result_dict.get('error', 'Unknown error')}")
                return error_msg, True
        except (json.JSONDecodeError, TypeError):
            # 结果不是 JSON，原样透传
            pass
        return result, False
    
    def chat(self, message: str, use_tools: bool = True,  
             temperature: float = 0.3, max_tokens: int = 2048, 
             stream: bool = False) -> str:
        """
        向模型发送消息，并在 ReAct 循环中处理工具调用

        Args:
            message: 用户消息
            use_tools: 是否启用工具调用
            temperature: 采样温度
            max_tokens: 最大生成 token 数
            stream: 是否流式返回响应

        Returns:
            模型的最终响应（流式模式下为生成器）
        """
        if stream:
            return self.chat_stream(message, use_tools, temperature, max_tokens)
        
        # 把用户消息加入历史
        self.conversation_history.append({"role": "user", "content": message})
        
        # 使用工具时准备带工具定义的系统提示词
        messages = []
        if use_tools:
            messages.append({
                "role": "system",
                "content": self._format_system_prompt_with_tools()
            })
        else:
            messages.append({
                "role": "system",
                "content": "You are a helpful assistant."
            })
        
        # 加入对话历史
        messages.extend(self.conversation_history)
        
        # 为 API 调用准备工具
        tools = self.tool_registry.get_tool_schemas() if use_tools else None
        
        # ReAct 循环——持续迭代直到不再需要工具调用
        max_iterations = 10  # 防止无限循环
        iteration = 0
        final_response = ""
        
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"ReAct iteration {iteration}")
            
            # 为本轮迭代准备消息
            messages = []
            if use_tools:
                messages.append({
                    "role": "system",
                    "content": self._format_system_prompt_with_tools()
                })
            else:
                messages.append({
                    "role": "system",
                    "content": "You are a helpful assistant."
                })
            messages.extend(self.conversation_history)
            
            # 调用模型
            response = self.client.chat.completions.create(
                model="Qwen/Qwen3-0.6B",
                messages=messages,
                tools=tools,
                tool_choice="auto" if use_tools else None,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            assistant_message = response.choices[0].message
            content = assistant_message.content or ""
            
            # 从结构化字段读取工具调用。开启 enable_auto_tool_choice 并使用
            # hermes 解析器时，vLLM 会把 <tool_call> 标签从文本中抽取出来
            # 放到这里，而不是留在 `content` 里（后者只包含 <think> 和最终正文）。
            tool_calls = []
            if use_tools and assistant_message.tool_calls:
                for tc in assistant_message.tool_calls:
                    raw_args = tc.function.arguments
                    try:
                        parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse tool arguments for {tc.function.name}: {e}")
                        parsed_args = {}
                    logger.info(f"Model requested tool call: {tc.function.name}({raw_args})")
                    tool_calls.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": parsed_args,
                        },
                    })
            
            if tool_calls:
                logger.info(f"Model requested {len(tool_calls)} tool call(s)")
                
                # 把带工具调用的 assistant 消息加入历史
                # （按 OpenAI API 规范，arguments 必须是 JSON 字符串）
                self.conversation_history.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            **tc,
                            "function": {
                                **tc["function"],
                                "arguments": tc["function"]["arguments"]
                                if isinstance(tc["function"]["arguments"], str)
                                else json.dumps(tc["function"]["arguments"])
                            }
                        }
                        for tc in tool_calls
                    ]
                })
                
                # 执行工具调用
                tool_results = self._execute_tool_calls(tool_calls)
                
                # 把工具结果加入对话
                for result in tool_results:
                    # 按 Qwen3 格式包装工具响应
                    tool_response = f'<tool_response>\n{result["content"]}\n</tool_response>'
                    self.conversation_history.append({
                        "role": "user",  # Qwen3 中工具响应当作 user 消息处理
                        "content": tool_response,
                        "name": result.get("name", "tool")
                    })
                
                # 继续 ReAct 循环
                continue
            else:
                # 没有工具调用——已得到最终响应
                self.conversation_history.append({
                    "role": "assistant",
                    "content": content
                })
                final_response = content
                break
        
        # 检查是否达到最大迭代次数
        if iteration >= max_iterations:
            logger.warning("Maximum iterations reached in ReAct loop")
            final_response = "I've reached the maximum number of reasoning steps. " + final_response
        
        return final_response
    
    def reset_conversation(self):
        """清空对话历史"""
        self.conversation_history = []
        logger.info("Conversation history reset")
    
    def chat_stream(self, message: str, use_tools: bool = True,
                    temperature: float = 0.3, max_tokens: int = 2048):
        """
        流式发送消息给模型，并在 ReAct 循环中处理工具调用

        逐个 yield 分片，包含：
        - type: 'thinking'、'tool_call'、'tool_result'、'content'
        - content: 实际内容
        """
        # 把用户消息加入历史
        self.conversation_history.append({"role": "user", "content": message})
        
        # 为 API 调用准备工具
        tools = self.tool_registry.get_tool_schemas() if use_tools else None
        
        # ReAct 循环——持续迭代直到不再需要工具调用
        max_iterations = 10  # 防止无限循环
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            logger.info(f"ReAct stream iteration {iteration}")
            
            # 为本轮迭代准备消息
            messages = []
            if use_tools:
                messages.append({
                    "role": "system",
                    "content": self._format_system_prompt_with_tools()
                })
            else:
                messages.append({
                    "role": "system",
                    "content": "You are a helpful assistant."
                })
            messages.extend(self.conversation_history)
            
            # 流式获取模型响应
            stream_response = self.client.chat.completions.create(
                model="Qwen/Qwen3-0.6B",
                messages=messages,
                tools=tools,
                tool_choice="auto" if use_tools else None,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )
            
            collected_content = []
            thinking_buffer = ""
            tool_call_parts = {}
            
            # 处理流式响应
            for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        content_chunk = delta.content
                        collected_content.append(content_chunk)
                        
                        # 判断是否为内部思考（<think> 标签之间的内容）
                        if '<think>' in content_chunk or thinking_buffer:
                            thinking_buffer += content_chunk
                            if '</think>' in thinking_buffer:
                                # 提取并输出思考内容
                                import re
                                thinking_match = re.search(r'<think>(.*?)</think>', thinking_buffer, re.DOTALL)
                                if thinking_match:
                                    # 逐字符流式输出思考内容
                                    for char in thinking_match.group(1).strip():
                                        yield {"type": "thinking", "content": char}
                                remaining = re.sub(
                                    r'<think>.*?</think>', '', thinking_buffer, flags=re.DOTALL
                                )
                                thinking_buffer = ""
                                if remaining:
                                    yield {"type": "content", "content": remaining}
                        else:
                            # 普通正文内容
                            yield {"type": "content", "content": content_chunk}

                    # vLLM 以分片形式流式返回结构化工具调用。id、名称和
                    # 参数可能分散在不同分片中，因此按 index 归并同一个调用。
                    for fragment in getattr(delta, "tool_calls", None) or []:
                        index = getattr(fragment, "index", None)
                        if index is None:
                            index = 0
                        buffered = tool_call_parts.setdefault(index, {
                            "id": None,
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        })
                        if getattr(fragment, "id", None):
                            buffered["id"] = fragment.id
                        if getattr(fragment, "type", None):
                            buffered["type"] = fragment.type
                        function = getattr(fragment, "function", None)
                        if function:
                            if getattr(function, "name", None):
                                buffered["function"]["name"] += function.name
                            if getattr(function, "arguments", None):
                                buffered["function"]["arguments"] += function.arguments

            # 在加入工具结果之前，把完整响应和结构化调用存入历史，
            # 与非流式路径的消息顺序保持一致。
            complete_response = ''.join(collected_content)

            if tool_call_parts:
                pending_tool_calls = []
                parse_errors = []
                assistant_tool_calls = []

                for index in sorted(tool_call_parts):
                    buffered = tool_call_parts[index]
                    call_id = buffered["id"] or str(uuid.uuid4())[:8]
                    tool_name = buffered["function"]["name"] or "unknown"
                    raw_args = buffered["function"]["arguments"] or "{}"
                    assistant_tool_calls.append({
                        "id": call_id,
                        "type": buffered["type"],
                        "function": {
                            "name": tool_name,
                            "arguments": raw_args,
                        },
                    })

                    try:
                        parsed_args = json.loads(raw_args)
                    except json.JSONDecodeError as e:
                        error_msg = f"❌ Tool call parse exception: {str(e)}"
                        logger.error(f"Tool call parse error: {e}")
                        parse_errors.append((tool_name, error_msg))
                        yield {"type": "tool_error", "content": error_msg}
                        continue

                    tool_data = {
                        "id": call_id,
                        "name": tool_name,
                        "arguments": parsed_args,
                    }
                    pending_tool_calls.append(tool_data)
                    yield {
                        "type": "tool_call",
                        "content": {
                            "name": tool_name,
                            "arguments": parsed_args,
                        },
                    }

                self.conversation_history.append({
                    "role": "assistant",
                    "content": complete_response,
                    "tool_calls": assistant_tool_calls,
                })

                for tool_name, error_msg in parse_errors:
                    self.conversation_history.append({
                        "role": "user",
                        "content": f'<tool_response>\n{error_msg}\n</tool_response>',
                        "name": tool_name,
                    })

                # 并行执行本轮所有合法的工具调用。
                if not pending_tool_calls:
                    outcomes = []
                elif len(pending_tool_calls) == 1:
                    outcomes = [self._execute_single_tool(pending_tool_calls[0])]
                else:
                    with ThreadPoolExecutor(max_workers=len(pending_tool_calls)) as executor:
                        outcomes = list(executor.map(self._execute_single_tool, pending_tool_calls))
                
                for tool_data, (result, is_error) in zip(pending_tool_calls, outcomes):
                    if is_error:
                        yield {"type": "tool_error", "content": result}
                    else:
                        yield {"type": "tool_result", "content": result}
                    
                    # 加入历史
                    self.conversation_history.append({
                        "role": "user",
                        "content": f'<tool_response>\n{result}\n</tool_response>',
                        "name": tool_data["name"]
                    })

                # 继续 ReAct 循环——让模型决定下一步
                continue
            else:
                # 没有工具调用——已得到最终响应
                self.conversation_history.append({
                    "role": "assistant",
                    "content": complete_response
                })
                # 退出 ReAct 循环
                break
        
        # 检查是否达到最大迭代次数
        if iteration >= max_iterations:
            yield {"type": "error", "content": "Maximum iterations reached in ReAct loop"}
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """获取当前对话历史"""
        return self.conversation_history
    
    def add_custom_tool(self, name: str, function: callable, 
                       description: str, parameters: Dict):
        """
        向注册表添加自定义工具

        Args:
            name: 工具名
            function: 可调用函数
            description: 工具描述
            parameters: OpenAI 风格的参数 schema
        """
        self.tool_registry.register_tool(name, function, description, parameters)
        logger.info(f"Added custom tool: {name}")


def demonstrate_tool_calling():
    """演示工具调用功能"""
    print("=" * 60)
    print("vLLM Tool Calling Demo with Qwen3")
    print("=" * 60)
    
    # 初始化 Agent
    agent = VLLMToolAgent()
    
    # 测试用例
    test_queries = [
        "What's the current temperature in Paris, France?",
        "Calculate 15 * 23 + sqrt(144)",
        "What time is it in Tokyo (JST)?",
        "Search for information about vLLM tool calling",
        "What's the weather in Dubai and what's 100 fahrenheit in celsius?",
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n--- Test {i} ---")
        print(f"User: {query}")
        
        response = agent.chat(query)
        print(f"Assistant: {response}")
        
        # 为下一个测试重置对话
        agent.reset_conversation()
        print("-" * 40)


if __name__ == "__main__":
    # 运行演示
    demonstrate_tool_calling()
