"""
上下文压缩研究 Agent（支持流式输出）
"""

import json
import logging
import time
import sys
from typing import List, Dict, Any, Optional, Generator, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from openai import OpenAI
from config import Config
from web_tools import WebTools
from compression_strategies import (
    CompressionStrategy,
    ContextCompressor,
    CompressedContent
)


def _reasoning_safe_temperature(model, requested=1.0):
    """思考型模型（Kimi K3、GPT-5 等）只接受 temperature=1。
    对这类模型返回 1；否则返回请求值，保持非思考型提供商
    （Doubao、DeepSeek、旧版 Moonshot）行为不变。"""
    m = str(model or "").lower().replace("/", "-")
    return 1 if ("kimi-k3" in m or "gpt-5" in m) else requested

# 配置日志
logging.basicConfig(level=logging.INFO, format=Config.LOG_FORMAT)
logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """表示一次工具调用"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    compressed_result: Optional[CompressedContent] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    # 提供商侧的 tool_call id，用于把历史中的 tool 消息关联回产生它的
    # 那次调用（窗口化压缩靠它找回原始查询）。
    id: Optional[str] = None


@dataclass
class AgentTrajectory:
    """记录 Agent 的执行轨迹"""
    tool_calls: List[ToolCall] = field(default_factory=list)
    total_tokens_used: int = 0
    prompt_tokens_used: int = 0
    completion_tokens_used: int = 0
    # 最近一次 API 调用的 prompt token 数 = 当前上下文规模。
    # 上面的 prompt_tokens_used 是累计成本计数器（每次调用的 prompt
    # 都会重复计入共享前缀），不能拿来与单次请求的上下文窗口比较。
    last_prompt_tokens: int = 0
    context_overflows: int = 0
    compression_strategy: CompressionStrategy = CompressionStrategy.NO_COMPRESSION
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None


class ResearchAgent:
    """
    带上下文压缩的研究型 AI Agent
    """
    
    def __init__(
        self, 
        api_key: str,
        compression_strategy: CompressionStrategy = CompressionStrategy.NO_COMPRESSION,
        verbose: bool = False,
        enable_streaming: bool = True
    ):
        """
        初始化研究 Agent

        参数:
            api_key: Moonshot/Kimi 的 API Key
            compression_strategy: 上下文压缩策略
            verbose: 启用详细日志
            enable_streaming: 启用流式响应
        """
        # Moonshot 官方 key 存在则直连；否则回退 OpenRouter（见 Config.resolve_llm）。
        resolved_key, resolved_base_url, resolved_model = Config.resolve_llm()
        self.client = OpenAI(
            api_key=resolved_key,
            base_url=resolved_base_url
        )
        self.model = resolved_model
        self.compression_strategy = compression_strategy
        self.verbose = verbose
        self.enable_streaming = enable_streaming
        
        # 初始化工具
        self.web_tools = WebTools()
        self.compressor = ContextCompressor(compression_strategy, api_key, enable_streaming)
        
        # 初始化轨迹
        self.trajectory = AgentTrajectory(compression_strategy=compression_strategy)
        
        # 初始化对话历史
        self.conversation_history = []
        self._init_system_prompt()
        
        logger.info(f"Agent initialized with compression strategy: {compression_strategy.value}")
    
    def _init_system_prompt(self):
        """初始化 OpenAI 联合创始人研究任务的系统提示词"""
        # 动态获取当前日期
        from datetime import datetime
        today = datetime.now()
        date_string = today.strftime("%A, %B %d, %Y")
        
        self.conversation_history = [
            {
                "role": "system",
                "content": f"""You are a research assistant tasked with finding information about OpenAI co-founders.

Your task is to:
1. First, search for and identify ALL OpenAI co-founders
2. Then, search for EACH co-founder individually to find their CURRENT affiliations
3. Compile a comprehensive report with current status for each co-founder

Important instructions:
- Be thorough and systematic - search for each person individually
- Focus on CURRENT affiliations, not historical roles
- Include company names, positions, and any recent changes
- If someone left a position, note where they went
- When you have gathered all information, provide a FINAL ANSWER with a complete list

Available tools:
- search_web: Search the web for information
- fetch_webpage: Fetch specific webpage content

Start by searching for the complete list of OpenAI co-founders.

TODAY'S DATE: {date_string}"""
            }
        ]
    
    def _get_tools_description(self) -> List[Dict[str, Any]]:
        """获取提供给模型的工具描述"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web for information. Returns multiple search results with content from each webpage.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return (default: 5)",
                                "default": 5
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "fetch_webpage",
                    "description": "Fetch and extract text content from a specific webpage URL",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL of the webpage to fetch"
                            }
                        },
                        "required": ["url"]
                    }
                }
            }
        ]
    
    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[Any, Optional[CompressedContent]]:
        """
        执行工具并返回结果（可选附带压缩）

        参数:
            tool_name: 要执行的工具名
            arguments: 工具参数

        返回:
            （工具结果, 压缩后内容（如适用））元组
        """
        if not isinstance(arguments, dict):
            arguments = {}

        if tool_name == "search_web":
            if "query" not in arguments:
                return {"error": "Missing required argument 'query' for search_web"}, None
            try:
                result = self.web_tools.search_web(**arguments)
            except Exception as e:
                logger.error(f"Failed to execute search_web: {e}")
                return {"error": f"Failed to execute search_web: {e}"}, None
            
            # 应用压缩策略
            query = arguments.get('query', '')
            current_context = self._get_current_context_summary()
            compressed = self.compressor.compress_search_results(
                result, 
                query, 
                current_context
            )
            
            return result, compressed
            
        elif tool_name == "fetch_webpage":
            if "url" not in arguments:
                return {"error": "Missing required argument 'url' for fetch_webpage"}, None
            try:
                result = self.web_tools.fetch_webpage(**arguments)
            except Exception as e:
                logger.error(f"Failed to execute fetch_webpage: {e}")
                return {"error": f"Failed to execute fetch_webpage: {e}"}, None
            
            # fetch_webpage 一般不压缩（供后续追问使用）
            return result, None
        else:
            return {"error": f"Unknown tool: {tool_name}"}, None
    
    def _get_current_context_summary(self) -> str:
        """获取当前上下文摘要，供上下文感知压缩使用"""
        if not self.trajectory.tool_calls:
            return ""
        
        # 取最近几次工具调用作为上下文
        recent_calls = self.trajectory.tool_calls[-3:]
        context_parts = []
        
        for call in recent_calls:
            context_parts.append(f"Previous search: {call.arguments.get('query', 'N/A')}")
        
        return " | ".join(context_parts)
    
    def _handle_windowed_compression(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        对消息历史应用窗口化压缩策略
        仅当上下文占用超过 80% 阈值时才压缩

        参数:
            messages: 当前消息历史

        返回:
            需要压缩时返回带压缩历史的消息列表
        """
        if self.compression_strategy != CompressionStrategy.WINDOWED_CONTEXT:
            return messages
        
        # 判断是否该开始压缩（上下文占用 80%）。
        # 用最近一次调用的 prompt 规模（当前上下文），而不是累计
        # 成本计数器——后者按平方增长，会在窗口真正接近占满之前
        # 很久就触发压缩。
        context_threshold = Config.CONTEXT_WINDOW_SIZE * 0.8

        if self.trajectory.last_prompt_tokens <= context_threshold:
            logger.debug(f"Windowed compression: Context usage below threshold ({self.trajectory.last_prompt_tokens:,}/{context_threshold:.0f} tokens)")
            return messages  # 还不需要压缩

        logger.info(f"⚠️ Context usage exceeds 80% threshold ({self.trajectory.last_prompt_tokens:,}/{Config.CONTEXT_WINDOW_SIZE} tokens) - Starting compression")
        
        # 压缩标记，用于识别已压缩过的消息
        COMPRESSION_MARKER = "[COMPRESSED]"
        
        # 先统计有多少条 tool 消息、其中多少条需要压缩
        tool_messages_to_compress = []
        already_compressed_count = 0
        
        for i, msg in enumerate(messages):
            if msg.get('role') == 'tool':
                original_content = msg.get('content', '')
                if original_content.startswith(COMPRESSION_MARKER):
                    already_compressed_count += 1
                else:
                    tool_messages_to_compress.append((i, msg))
        
        total_tool_messages = already_compressed_count + len(tool_messages_to_compress)
        
        if not tool_messages_to_compress:
            logger.debug(f"Windowed compression: All {total_tool_messages} tool messages already compressed")
            return messages  # 所有 tool 消息都已压缩
        
        logger.info(f"📊 Compressing {len(tool_messages_to_compress)} uncompressed tool messages (out of {total_tool_messages} total)")
        
        # 对所有未压缩的 tool 消息执行压缩，并组装结果
        compressed_messages = []
        compressed_in_this_pass = 0
        
        for i, msg in enumerate(messages):
            if msg.get('role') == 'tool':
                original_content = msg.get('content', '')
                
                # 检查是否已压缩
                if original_content.startswith(COMPRESSION_MARKER):
                    # 已压缩，原样保留
                    compressed_messages.append(msg)
                else:
                    # 压缩这条工具结果
                    compressed_in_this_pass += 1
                    
                    # 找到对应的工具调用记录以获取上下文
                    tool_call_id = msg.get('tool_call_id')
                    query = "Information search"  # 默认值
                    
                    # 尝试从工具调用记录中找回查询
                    for call in self.trajectory.tool_calls:
                        if call.id is not None and call.id == tool_call_id:
                            query = call.arguments.get('query', query)
                            break
                    
                    logger.debug(f"Compressing tool message {compressed_in_this_pass}/{len(tool_messages_to_compress)} at index {i} (query: {query[:50]}...)")
                    compressed = self.compressor.compress_for_history(
                        original_content,
                        'search_web',
                        query,
                        preserve_citations=True
                    )
                    logger.debug(f"Compressed: {compressed.original_length:,} → {compressed.compressed_length:,} chars")
                    
                    # 用明确的标记注明已压缩
                    compressed_content = (
                        f"{COMPRESSION_MARKER} "
                        f"[Original: {compressed.original_length:,} chars → Compressed: {compressed.compressed_length:,} chars]\n"
                        f"{compressed.content}"
                    )
                    
                    compressed_messages.append({
                        **msg,
                        'content': compressed_content
                    })
            else:
                compressed_messages.append(msg)
        
        logger.info(f"✅ Compressed {compressed_in_this_pass} tool messages in this pass")
        
        return compressed_messages
    
    def _stream_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        以流式方式获取模型响应

        参数:
            messages: 对话消息

        返回:
            完整的消息对象（含 token 用量）
        """
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self._get_tools_description(),
                tool_choice="auto",
                temperature=_reasoning_safe_temperature(self.model, Config.MODEL_TEMPERATURE),
                max_tokens=Config.MODEL_MAX_TOKENS,
                stream=True,
                stream_options={"include_usage": True}  # 请求在流中返回 token 用量
            )
            
            collected_chunks = []
            collected_messages = []
            current_tool_calls = []
            usage_data = None
            
            print("\n🤖 Assistant: ", end="", flush=True)
            
            for chunk in stream:
                collected_chunks.append(chunk)
                
                # 若出现 usage 数据则捕获（可能在不含 choices 的 chunk 里）
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    usage_data = chunk.usage
                
                # 访问前先确认 chunk 带 choices
                if hasattr(chunk, 'choices') and chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    
                    # 处理正文内容
                    if hasattr(delta, 'content') and delta.content:
                        content = delta.content
                        print(content, end="", flush=True)
                        collected_messages.append(content)
                    
                    # 处理流式传输中的工具调用
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tool_call_delta in delta.tool_calls:
                            if tool_call_delta.index is not None:
                                # 确保列表中的工具调用槽位足够
                                while len(current_tool_calls) <= tool_call_delta.index:
                                    current_tool_calls.append({
                                        "id": "",
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""}
                                    })
                                
                                if tool_call_delta.id:
                                    current_tool_calls[tool_call_delta.index]["id"] = tool_call_delta.id
                                if tool_call_delta.function:
                                    if tool_call_delta.function.name:
                                        current_tool_calls[tool_call_delta.index]["function"]["name"] = tool_call_delta.function.name
                                    if tool_call_delta.function.arguments:
                                        current_tool_calls[tool_call_delta.index]["function"]["arguments"] += tool_call_delta.function.arguments
            
            print("\n", flush=True)
            
            # 如有 token 用量则记录日志
            if usage_data:
                prompt_tokens = usage_data.prompt_tokens if hasattr(usage_data, 'prompt_tokens') else 0
                completion_tokens = usage_data.completion_tokens if hasattr(usage_data, 'completion_tokens') else 0
                total_tokens = usage_data.total_tokens if hasattr(usage_data, 'total_tokens') else 0
                
                logger.info(f"🔢 Kimi API Token Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}")

                # 更新轨迹
                self.trajectory.last_prompt_tokens = prompt_tokens
                self.trajectory.prompt_tokens_used += prompt_tokens
                self.trajectory.completion_tokens_used += completion_tokens
                self.trajectory.total_tokens_used += total_tokens
            
            # 组装完整消息
            complete_message = {
                "role": "assistant",
                "content": "".join(collected_messages) if collected_messages else None
            }
            
            if current_tool_calls:
                complete_message["tool_calls"] = current_tool_calls
            
            return complete_message
            
        except Exception as e:
            logger.error(f"Error in streaming response: {str(e)}")
            raise
    
    def _non_streaming_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        以非流式方式获取模型响应

        参数:
            messages: 对话消息

        返回:
            完整的消息对象（含 token 用量）
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self._get_tools_description(),
            tool_choice="auto",
            temperature=_reasoning_safe_temperature(self.model, Config.MODEL_TEMPERATURE),
            max_tokens=Config.MODEL_MAX_TOKENS,
            stream=False
        )
        
        message = response.choices[0].message
        
        # 记录 token 用量
        if hasattr(response, 'usage') and response.usage:
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens
            total_tokens = response.usage.total_tokens
            
            logger.info(f"🔢 Kimi API Token Usage - Prompt: {prompt_tokens}, Completion: {completion_tokens}, Total: {total_tokens}")

            # 更新轨迹
            self.trajectory.last_prompt_tokens = prompt_tokens
            self.trajectory.prompt_tokens_used += prompt_tokens
            self.trajectory.completion_tokens_used += completion_tokens
            self.trajectory.total_tokens_used += total_tokens
        
        # 转为字典格式
        message_dict = {
            "role": "assistant",
            "content": message.content
        }
        
        if hasattr(message, 'tool_calls') and message.tool_calls:
            message_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in message.tool_calls
            ]
        
        # 展示响应
        if message.content:
            print(f"\n🤖 Assistant: {message.content}\n")
        
        return message_dict
    
    def execute_research(self, max_iterations: int = 15) -> Dict[str, Any]:
        """
        执行研究任务

        参数:
            max_iterations: 最大工具调用轮数

        返回:
            研究结果
        """
        # 加入初始用户消息
        self.conversation_history.append({
            "role": "user",
            "content": "Please research and find the current affiliations of all OpenAI co-founders."
        })
        
        messages = self.conversation_history.copy()
        iteration = 0
        final_answer = None
        
        print("\n" + "="*60)
        print(f"Starting research with {self.compression_strategy.value} strategy")
        print("="*60)
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n📍 Iteration {iteration}/{max_iterations}")
            
            try:
                # 需要时应用窗口化压缩
                if self.compression_strategy == CompressionStrategy.WINDOWED_CONTEXT:
                    messages = self._handle_windowed_compression(messages)
                
                # 展示轨迹中当前累计的 token 用量
                print(f"📊 Cumulative Token Usage - Prompt: {self.trajectory.prompt_tokens_used:,}, Completion: {self.trajectory.completion_tokens_used:,}, Total: {self.trajectory.total_tokens_used:,}")
                
                # 按真实用量判断是否逼近 token 上限
                if self.trajectory.total_tokens_used > 0:  # 仅在首轮调用之后检查
                    # 压缩演示使用 128k 上下文预算。用最近一次调用的
                    # prompt 规模（真实上下文）对比窗口——累计计数器每次
                    # 调用都会重复计入共享前缀，会按平方高估用量。
                    if self.trajectory.last_prompt_tokens > Config.CONTEXT_WINDOW_SIZE * 0.8:
                        logger.warning(f"Approaching context limit: {self.trajectory.last_prompt_tokens:,} prompt tokens in last request")
                        self.trajectory.context_overflows += 1

                        if self.compression_strategy == CompressionStrategy.NO_COMPRESSION:
                            print("\n⚠️ Context overflow detected! This demonstrates the limitation of no compression.")
                            return {
                                "error": f"Context window exceeded - {self.trajectory.last_prompt_tokens:,} tokens in last request (limit: {Config.CONTEXT_WINDOW_SIZE})",
                                "trajectory": self.trajectory,
                                "iterations": iteration
                            }
                
                # 获取模型响应
                if self.enable_streaming:
                    message = self._stream_response(messages)
                else:
                    message = self._non_streaming_response(messages)
                
                # 处理工具调用
                if message.get('tool_calls'):
                    messages.append(message)

                    if message.get('content'):
                        print(f"\n🤖 Assistant: {message['content']}")
                    
                    for tool_call in message['tool_calls']:
                        function_name = tool_call['function']['name']
                        raw_args = tool_call['function'].get('arguments') or "{}"
                        try:
                            if isinstance(raw_args, dict):
                                function_args = raw_args
                            elif isinstance(raw_args, (bytes, bytearray)):
                                function_args = json.loads(raw_args.decode("utf-8"))
                            elif isinstance(raw_args, str):
                                function_args = json.loads(raw_args)
                            else:
                                function_args = json.loads(str(raw_args))

                            if not isinstance(function_args, dict):
                                logger.warning(
                                    "Tool argument JSON is not an object, proceeding with empty object: %r",
                                    raw_args,
                                )
                                function_args = {}
                        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
                            # 容忍非法的工具参数 JSON，保住循环不中断。
                            function_args = {}
                            logger.warning(
                                "Tool argument is not valid JSON, proceeding with empty object: %r",
                                raw_args,
                            )
                        
                        print(f"\n🔧 Executing: {function_name}")
                        print(f"   Args: {function_args}")
                        
                        # 执行工具
                        result, compressed = self._execute_tool(function_name, function_args)
                        
                        # 记录工具调用
                        tool_call_record = ToolCall(
                            tool_name=function_name,
                            arguments=function_args,
                            result=result,
                            compressed_result=compressed,
                            id=tool_call['id']
                        )
                        self.trajectory.tool_calls.append(tool_call_record)
                        
                        # 决定写入消息的内容
                        if compressed and self.compression_strategy != CompressionStrategy.NO_COMPRESSION:
                            # 使用压缩后的内容
                            tool_content = compressed.content
                            print(f"   ✂️ Compressed: {compressed.original_length:,} → {compressed.compressed_length:,} chars")
                        else:
                            # 使用原始内容（不压缩，或窗口化策略下的最新消息）
                            if function_name == "search_web":
                                # 格式化搜索结果
                                tool_content = json.dumps(result, indent=2)
                            else:
                                tool_content = json.dumps(result)
                        
                        # 把工具结果加入消息
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call['id'],
                            "content": tool_content
                        }
                        messages.append(tool_msg)
                        
                        print(f"   📄 Result size: {len(tool_content):,} characters")
                
                elif message.get('content'):
                    # 无工具调用，只有文本内容
                    messages.append(message)
                    final_answer = message['content']
                    logger.info("Final answer found")
                    break
                    
            except Exception as e:
                logger.error(f"Error during research: {str(e)}")
                return {
                    "error": str(e),
                    "trajectory": self.trajectory,
                    "iterations": iteration
                }
        
        # 记录结束时间
        self.trajectory.end_time = time.time()
        
        return {
            "final_answer": final_answer,
            "trajectory": self.trajectory,
            "iterations": iteration,
            "success": final_answer is not None,
            "execution_time": self.trajectory.end_time - self.trajectory.start_time
        }
    
    def reset(self):
        """重置 Agent 状态"""
        self.trajectory = AgentTrajectory(compression_strategy=self.compression_strategy)
        self._init_system_prompt()
        self.web_tools.clear_cache()
        logger.info("Agent state reset")
