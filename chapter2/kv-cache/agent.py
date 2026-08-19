"""
KV Cache 演示 Agent（ReAct 模式）
通过正确与错误两类实现演示 KV cache 的重要性。
使用本地文件系统工具读取和检索代码文件。
"""

import json
import os
import re
import time
import logging
import random
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from openai import OpenAI
import glob as glob_module
import subprocess

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _is_reasoning_model(model) -> bool:
    """判断是否为输出 reasoning_content 且只接受 temperature=1 的模型。

    在 Moonshot 线上端点上，当前整个 Kimi 家族都会思考：
    kimi-k2.5 / kimi-k2.6 / kimi-k2.7* / kimi-k3。旧的 moonshot-v1-*
    对话模型不思考（也不上报 cached_tokens）。"""
    m = str(model or "").lower().replace("/", "-")
    if "gpt-5" in m:
        return True
    return any(tag in m for tag in ("kimi-k2.5", "kimi-k2.6", "kimi-k2.7", "kimi-k3"))


def _reasoning_safe_temperature(model, requested=1.0):
    """思考型模型（Kimi K2.5/K2.6/K2.7/K3、GPT-5 等）只接受 temperature=1。
    对这类模型返回 1；否则返回请求值，让非思考型提供商
    （moonshot-v1、Doubao、DeepSeek）行为不变。"""
    return 1 if _is_reasoning_model(model) else requested


def _reasoning_safe_max_tokens(model, requested=2000):
    """思考型模型在输出内容/工具调用之前，会先把 completion 预算花在
    隐藏的思考 token 上。给它们留足余量，避免工具调用被截断；
    非思考型模型保持不变。"""
    return max(requested, 4096) if _is_reasoning_model(model) else requested


# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class KVCacheMode(Enum):
    """各种 KV cache 优化模式"""
    CORRECT = "correct"  # 正确实现：上下文稳定
    DYNAMIC_SYSTEM = "dynamic_system"  # 系统提示词带时间戳且每次变化
    SHUFFLED_TOOLS = "shuffled_tools"  # 每次请求打乱工具顺序
    DYNAMIC_PROFILE = "dynamic_profile"  # 用户画像（积分余额）不断变化
    SLIDING_WINDOW = "sliding_window"  # 只保留最近 6 条消息
    TEXT_FORMAT = "text_format"  # 把消息格式化为纯文本


@dataclass
class ToolCall:
    """表示一次工具调用"""
    name: str
    arguments: Dict[str, Any]
    result: Any = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentMetrics:
    """Agent 性能指标"""
    ttft: float = 0.0  # 首 token 时间 TTFT（第一次迭代）
    ttft_per_iteration: List[float] = field(default_factory=list)  # 每次迭代的 TTFT
    total_time: float = 0.0
    iterations: int = 0
    tool_calls: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0


class LocalFileTools:
    """本地文件系统工具实现"""
    
    def __init__(self, root_dir: str = "."):
        self.root_dir = os.path.abspath(root_dir)
        logger.info(f"File tools initialized with root: {self.root_dir}")
    
    def read_file(self, file_path: str, offset: int = 0, size: int = None) -> Dict[str, Any]:
        """
        读取文件内容
        
        参数:
            file_path: 相对根目录的文件路径
            offset: 起始行号（从 0 开始，默认: 0）
            size: 读取的行数（默认: None，读取全部）
            
        返回:
            包含文件内容或错误的字典
        """
        try:
            full_path = os.path.join(self.root_dir, file_path)
            
            # 安全检查 —— 确保路径在 root_dir 之内
            real_path = os.path.realpath(full_path)
            if not real_path.startswith(self.root_dir):
                return {
                    "error": f"Access denied: Path outside root directory",
                    "success": False
                }
            
            with open(real_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            
            # 应用 offset 和 size
            if offset < 0:
                offset = 0
            if offset >= total_lines:
                return {
                    "path": file_path,
                    "content": "",
                    "total_lines": total_lines,
                    "lines_read": 0,
                    "offset": offset,
                    "success": True,
                    "message": f"Offset {offset} exceeds file length ({total_lines} lines)"
                }
            
            # 确定结束行
            if size is None or size < 0:
                # 负 size 是常见的"读全部"哨兵值；避免 lines[i:-n] 的写法。
                end = total_lines
            else:
                end = min(offset + size, total_lines)
            
            # 取出请求的行
            selected_lines = lines[offset:end]
            content = ''.join(selected_lines)
            
            # 出于安全考虑限制大小（10KB）
            truncated = False
            if len(content) > 10000:
                content = content[:10000]
                truncated = True
            
            return {
                "path": file_path,
                "content": content,
                "total_lines": total_lines,
                "lines_read": len(selected_lines),
                "offset": offset,
                "end_line": end,
                "truncated": truncated,
                "success": True
            }
        except FileNotFoundError:
            return {
                "error": f"File not found: {file_path}",
                "success": False
            }
        except Exception as e:
            return {
                "error": f"Error reading file: {str(e)}",
                "success": False
            }
    
    def find(self, pattern: str = "*", directory: str = ".") -> Dict[str, Any]:
        """
        查找匹配模式的文件（类似 Unix 的 find 命令）
        
        参数:
            pattern: 文件名模式（支持通配符，默认: "*" 匹配所有文件）
            directory: 要搜索的目录（相对 root_dir）
            
        返回:
            包含匹配文件列表的字典
        """
        try:
            # 正确处理目录路径
            if directory == ".":
                search_dir = self.root_dir
            else:
                # 统一去掉首尾斜杠
                directory = directory.strip('/')
                search_dir = os.path.join(self.root_dir, directory)
            
            # 安全检查
            real_path = os.path.realpath(search_dir)
            if not real_path.startswith(self.root_dir):
                return {
                    "error": f"Access denied: Path outside root directory",
                    "success": False
                }
            
            # 检查目录是否存在
            if not os.path.exists(real_path):
                return {
                    "error": f"Directory not found: {directory}",
                    "success": False
                }
            
            # 用 glob 查找匹配的文件
            matches = []
            for root, dirs, files in os.walk(real_path):
                # 过滤隐藏目录和 __pycache__
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                
                for file in files:
                    # 跳过隐藏文件和 .pyc 文件
                    if file.startswith('.') or file.endswith('.pyc'):
                        continue
                        
                    if glob_module.fnmatch.fnmatch(file, pattern):
                        # 取相对 root_dir（而非 search_dir）的路径
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, self.root_dir)
                        matches.append(rel_path)
            
            # 排序，保证结果稳定
            matches.sort()
            
            # 演示用途，限制结果数量
            if len(matches) > 100:
                matches = matches[:100]
                truncated = True
            else:
                truncated = False
            
            return {
                "pattern": pattern,
                "directory": directory,
                "matches": matches,
                "count": len(matches),
                "truncated": truncated,
                "success": True
            }
        except Exception as e:
            return {
                "error": f"Error finding files: {str(e)}",
                "success": False
            }
    
    def grep(self, pattern: str, file_path: str = None, directory: str = None) -> Dict[str, Any]:
        """
        在文件中搜索模式（类似 Unix 的 grep 命令）
        
        参数:
            pattern: 要搜索的正则表达式
            file_path: 要搜索单个文件（可选）
            directory: 要搜索的目录（可选）
            
        返回:
            包含匹配行的字典
        """
        try:
            matches = []
            files_searched = []
            
            if file_path:
                # 在单个文件中搜索
                full_path = os.path.join(self.root_dir, file_path)
                real_path = os.path.realpath(full_path)
                
                if not real_path.startswith(self.root_dir):
                    return {
                        "error": f"Access denied: Path outside root directory",
                        "success": False
                    }
                
                files_to_search = [file_path]
            elif directory:
                # 在目录中搜索
                search_dir = os.path.join(self.root_dir, directory)
                real_path = os.path.realpath(search_dir)
                
                if not real_path.startswith(self.root_dir):
                    return {
                        "error": f"Access denied: Path outside root directory",
                        "success": False
                    }
                
                # 找出目录下所有文本文件
                files_to_search = []
                for root, dirs, files in os.walk(real_path):
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for file in files:
                        if file.endswith(('.py', '.txt', '.md', '.json', '.yaml', '.yml', '.js', '.ts', '.jsx', '.tsx')):
                            rel_path = os.path.relpath(os.path.join(root, file), self.root_dir)
                            files_to_search.append(rel_path)
                            if len(files_to_search) >= 50:  # 演示用途，限制文件数量
                                break
            else:
                return {
                    "error": "Must specify either file_path or directory",
                    "success": False
                }
            
            # 编译正则表达式
            regex = re.compile(pattern, re.IGNORECASE)
            
            # 在文件中搜索
            for file in files_to_search:
                full_path = os.path.join(self.root_dir, file)
                try:
                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        for i, line in enumerate(lines, 1):
                            if regex.search(line):
                                matches.append({
                                    "file": file,
                                    "line_num": i,
                                    "line": line.strip()[:200]  # 截断过长的行
                                })
                                if len(matches) >= 100:  # 限制匹配数量
                                    break
                    files_searched.append(file)
                except Exception:
                    continue
                
                if len(matches) >= 100:
                    break
            
            return {
                "pattern": pattern,
                "matches": matches,
                "files_searched": len(files_searched),
                "match_count": len(matches),
                "truncated": len(matches) >= 100,
                "success": True
            }
        except Exception as e:
            return {
                "error": f"Error searching: {str(e)}",
                "success": False
            }


class KVCacheAgent:
    """
    支持不同 KV cache 优化模式的 ReAct Agent
    """
    
    def __init__(self, api_key: str, mode: KVCacheMode = KVCacheMode.CORRECT,
                 model: str = "kimi-k2.6", root_dir: str = ".",
                 verbose: bool = True):
        """
        初始化 Agent
        
        参数:
            api_key: Moonshot/Kimi 的 API key
            mode: KV cache 优化模式
            model: 使用的模型
            root_dir: 文件操作的根目录
            verbose: 为 True 时记录详细信息
        """
        # 默认走 Moonshot/Kimi 官方端点；若传入的是 OpenRouter key（sk-or-…），
        # 则自动回退到 OpenRouter，并把 kimi-* 模型名映射为 moonshotai/kimi-k2。
        # 端点、key 与模型名映射统一由 agentbook 的 provider 注册表维护；
        # “这把 key 属于谁”只有调用方知道，因此在此处判定后再交给注册表解析。
        from agentbook.providers import is_openrouter_key, resolve_backend

        provider = "openrouter" if is_openrouter_key(api_key) else "kimi"
        backend = resolve_backend(provider, model=model, api_key=api_key)
        self.client = OpenAI(
            api_key=backend.api_key,
            base_url=backend.base_url
        )
        self.model = backend.model
        self.mode = mode
        self.verbose = verbose
        self.tools = LocalFileTools(root_dir)
        
        # 初始化对话历史
        self.conversation_history = []
        self.user_credits = 100  # 供 dynamic profile 模式使用
        self.metrics = AgentMetrics()
        
        # OpenAI 格式的工具定义
        self.tool_definitions = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the contents of a file, optionally specifying a line range",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file relative to root directory"
                            },
                            "offset": {
                                "type": "integer",
                                "description": "Line number to start reading from (0-based, default: 0)",
                                "default": 0
                            },
                            "size": {
                                "type": "integer",
                                "description": "Number of lines to read (default: read all lines)",
                                "default": None
                            }
                        },
                        "required": ["file_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find",
                    "description": "Find files matching a pattern",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "File name pattern (supports wildcards like *.py)"
                            },
                            "directory": {
                                "type": "string",
                                "description": "Directory to search in (default: current directory)",
                                "default": "."
                            }
                        },
                        "required": ["pattern"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "grep",
                    "description": "Search for a pattern in files",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Regular expression pattern to search for"
                            },
                            "file_path": {
                                "type": "string",
                                "description": "Single file to search in (optional)"
                            },
                            "directory": {
                                "type": "string",
                                "description": "Directory to search in (optional)"
                            }
                        },
                        "required": ["pattern"]
                    }
                }
            }
        ]
        
        logger.info(f"Agent initialized with mode: {mode.value}, model: {model}")
    
    def _get_system_prompt(self) -> str:
        """按模式返回系统提示词"""
        base_prompt = """You are a helpful AI assistant with access to file system tools.
You can read files, find files by pattern, and search for text within files.
Use the ReAct pattern: Reason about what to do, then Act using tools, and Observe the results.

When asked to analyze or summarize code projects, be thorough:
1. First use 'find' to discover the structure
2. Then read key files to understand the content
3. Use 'grep' to search for specific patterns if needed
4. Once you have gathered sufficient information, provide your response

Always think step by step and use tools to gather information. When you have enough information to answer the user's question, simply provide your response without calling any tools."""
        
        if self.mode == KVCacheMode.DYNAMIC_SYSTEM:
            # 在系统提示词中加入时间戳（破坏 KV cache）
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            return f"{base_prompt}\n\nCURRENT TIME: {timestamp}"
        
        return base_prompt
    
    def _get_tools(self) -> List[Dict]:
        """按模式返回工具定义"""
        tools = self.tool_definitions.copy()
        
        if self.mode == KVCacheMode.SHUFFLED_TOOLS:
            # 打乱工具顺序（破坏 KV cache）
            random.shuffle(tools)
        
        return tools
    
    def _get_user_profile_message(self) -> Optional[Dict]:
        """返回 dynamic profile 模式用的用户画像消息"""
        if self.mode == KVCacheMode.DYNAMIC_PROFILE:
            self.user_credits -= 1
            return {
                "role": "user",
                "content": f"[User Profile: Premium user with {self.user_credits} credits remaining]"
            }
        return None
    
    def _format_messages(self, task: str) -> List[Dict]:
        """按模式构造消息列表 —— 错误模式下每轮重建"""
        messages = []
        
        # 加入系统提示词（DYNAMIC_SYSTEM 模式下每次都变）
        messages.append({
            "role": "system",
            "content": self._get_system_prompt()
        })
        
        # dynamic profile 模式下加入用户画像（每次都变）
        profile_msg = self._get_user_profile_message()
        if profile_msg:
            messages.append(profile_msg)
        
        if self.mode == KVCacheMode.SLIDING_WINDOW:
            # 只保留最近 6 条历史消息（窗口）。
            # conversation_history 存的是 assistant/tool 消息，直接切片可能
            # 以一条 tool 消息开头，而与其配对的 assistant tool_calls 消息
            # 已被裁掉 —— API 会拒绝这样的历史。因此把窗口起点向前回退到
            # 所属的 assistant 消息，保证每条 tool 消息都有配对。
            if self.conversation_history:
                start = max(0, len(self.conversation_history) - 6)
                while start > 0 and self.conversation_history[start].get("role") == "tool":
                    start -= 1
                messages.extend(self.conversation_history[start:])
        elif self.mode == KVCacheMode.TEXT_FORMAT:
            # 把全部历史格式化为纯文本（破坏 KV cache）
            # 每次重新格式化会破坏结构化格式
            if self.conversation_history:
                history_text = "Previous conversation:\n"
                for msg in self.conversation_history:
                    role = msg['role'].upper()
                    
                    # 处理不同类型的消息
                    if role == "ASSISTANT":
                        # 同时带上文本内容
                        if msg.get('content'):
                            history_text += f"{role}: {msg['content']}\n"
                        # 检查工具调用
                        if msg.get('tool_calls'):
                            history_text += f"{role}: [Making tool calls]\n"
                            for tool_call in msg['tool_calls']:
                                func_name = tool_call.get('function', {}).get('name', 'unknown')
                                func_args = tool_call.get('function', {}).get('arguments', '{}')
                                history_text += f"  - Calling {func_name} with args: {func_args}\n"
                    elif role == "TOOL":
                        # 格式化工具响应
                        tool_content = msg.get('content', '')
                        history_text += f"TOOL RESPONSE: {tool_content}\n"
                    else:
                        # USER、SYSTEM 等其他角色
                        content = msg.get('content', '')
                        if content:
                            history_text += f"{role}: {content}\n"
                
                messages.append({
                    "role": "user",
                    "content": history_text
                })
        else:
            # CORRECT、DYNAMIC_SYSTEM、SHUFFLED_TOOLS、DYNAMIC_PROFILE 模式
            # 包含完整对话历史
            messages.extend(self.conversation_history)
        
        # 当前任务始终加在末尾
        messages.append({
            "role": "user",
            "content": task
        })
        
        return messages
    
    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """执行工具并返回结果"""
        tool_map = {
            "read_file": self.tools.read_file,
            "find": self.tools.find,
            "grep": self.tools.grep
        }
        
        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}", "success": False}
        
        try:
            # 过滤意外传入的参数
            tool_func = tool_map[tool_name]
            # 获取该工具接受的参数
            import inspect
            sig = inspect.signature(tool_func)
            valid_args = {}
            for param_name in sig.parameters:
                if param_name in arguments:
                    valid_args[param_name] = arguments[param_name]
            
            # 有参数被过滤时记录日志
            filtered = set(arguments.keys()) - set(valid_args.keys())
            if filtered and self.verbose:
                logger.warning(f"Filtered unexpected arguments for {tool_name}: {filtered}")
            
            return tool_func(**valid_args)
        except Exception as e:
            # 错误作为工具结果返回，而不是抛异常
            error_msg = f"Tool execution error: {str(e)}"
            logger.error(f"{tool_name} failed: {error_msg}")
            return {"error": error_msg, "success": False}
    
    
    def execute_task(self, task: str, max_iterations: int = 50) -> Dict[str, Any]:
        """
        用标准 OpenAI 工具调用按 ReAct 模式执行任务
        
        参数:
            task: 要执行的任务
            max_iterations: 最大迭代次数
            
        返回:
            含指标的任务执行结果
        """
        start_time = time.time()
        iteration = 0
        final_answer = None
        tool_calls = []
        
        # 保存原始任务
        original_task = task
        
        while iteration < max_iterations:
            iteration += 1
            
            # 关键：为演示 KV cache 而设计的消息处理方式
            # 
            # CORRECT 模式：首次迭代构造一次 messages，之后只做追加
            #   - 上下文保持稳定 → KV cache 高效工作
            # 
            # 错误模式：每轮迭代都从历史重建整个 messages 列表
            #   - 被迫完整重建上下文 → KV cache 失效
            #   - 单轮迭代内仍会向 messages 追加，保证 API 流程正确
            #   - 但每轮新迭代开始时都会从头重建
            
            if self.mode == KVCacheMode.CORRECT:
                # 正确模式：messages 只构造一次，之后复用同一列表
                if iteration == 1:
                    messages = self._format_messages(original_task)
            else:
                # 错误模式：每轮迭代都从历史重建 messages
                # 上下文变化会强制缓存失效
                messages = self._format_messages(original_task)
            
            # 准备请求
            request_data = {
                "model": self.model,
                "messages": messages,
                "temperature": _reasoning_safe_temperature(self.model, 0.7),
                "max_tokens": _reasoning_safe_max_tokens(self.model, 2000)
            }
            
            # 所有模式都带上工具（TEXT_FORMAT 也需要工具才能工作）
            # TEXT_FORMAT 只影响历史的格式化方式，不影响工具可用性
            request_data["tools"] = self._get_tools()
            request_data["tool_choice"] = "auto"
            
            # 发起 API 调用
            api_start = time.time()
            try:
                response = self.client.chat.completions.create(**request_data)
                
                # 记录本轮迭代的 TTFT
                iteration_ttft = time.time() - api_start
                self.metrics.ttft_per_iteration.append(iteration_ttft)
                
                # 单独记录首次迭代的 TTFT，保持向后兼容
                if iteration == 1:
                    self.metrics.ttft = iteration_ttft
                
                # 提取响应
                message = response.choices[0].message
                
                # 把 assistant 内容打印到控制台（始终显示，不限 verbose）
                if message.content:
                    print(f"\n🤖 Assistant (Iteration {iteration}):")
                    print("-" * 40)
                    print(message.content)
                    print("-" * 40)
                
                # 记录 token 用量与缓存信息
                if hasattr(response, 'usage'):
                    usage = response.usage
                    self.metrics.prompt_tokens += usage.prompt_tokens
                    self.metrics.completion_tokens += usage.completion_tokens
                    
                    # 检查缓存的 token（Kimi 特有）
                    # cached_tokens 字段直接出现在 usage 对象上
                    cached = 0
                    if hasattr(usage, 'cached_tokens'):
                        # usage 对象上的直接属性
                        cached = usage.cached_tokens if usage.cached_tokens is not None else 0
                        self.metrics.cached_tokens += cached
                        if cached > 0:
                            self.metrics.cache_hits += 1
                        else:
                            self.metrics.cache_misses += 1
                    else:
                        # 尝试其他位置
                        if hasattr(usage, 'prompt_tokens_details'):
                            details = usage.prompt_tokens_details
                            if details and hasattr(details, 'cached_tokens'):
                                cached = details.cached_tokens if details.cached_tokens is not None else 0
                                self.metrics.cached_tokens += cached
                                if cached > 0:
                                    self.metrics.cache_hits += 1
                                else:
                                    self.metrics.cache_misses += 1
                        
                        # verbose 且未找到缓存字段时的调试日志
                        if self.verbose and iteration > 1 and cached == 0:
                            logger.debug(f"Usage object attributes: {dir(usage)}")
                            logger.debug(f"Usage data: {usage}")
                    
                    if self.verbose:
                        # 记录本轮的 TTFT
                        cache_info = f", cached={cached}" if cached > 0 else ""
                        logger.info(f"Iteration {iteration} - TTFT: {iteration_ttft:.3f}s, "
                                  f"Tokens: prompt={usage.prompt_tokens}, "
                                  f"completion={usage.completion_tokens}"
                                  f"{cache_info}")
                
                # 按标准 OpenAI 格式处理工具调用
                if hasattr(message, 'tool_calls') and message.tool_calls:
                    # 加入带工具调用的 assistant 消息
                    # 始终追加到本轮的 messages
                    messages.append(message.model_dump())
                    # 同时追加到历史，供下一轮使用
                    self.conversation_history.append(message.model_dump())
                    
                    for tool_call in message.tool_calls:
                        function_name = tool_call.function.name
                        
                        # 安全解析参数
                        try:
                            function_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse tool arguments: {e}")
                            function_args = {}
                            result = {"error": f"Invalid tool arguments: {str(e)}", "success": False}
                        else:
                            if self.verbose:
                                logger.info(f"Executing tool: {function_name} with args: {function_args}")
                            
                            # 执行工具（错误在内部处理并作为结果返回）
                            result = self._execute_tool(function_name, function_args)
                        
                        # 记录工具调用
                        tc = ToolCall(name=function_name, arguments=function_args, result=result)
                        tool_calls.append(tc)
                        
                        # 打印工具结果摘要
                        if result.get("success"):
                            # 成功 —— 显示简要摘要
                            if function_name == "read_file":
                                lines_info = f"{result.get('lines_read', 'unknown')} lines"
                                if result.get('offset', 0) > 0 or result.get('size'):
                                    lines_info += f" (lines {result.get('offset', 0)}-{result.get('end_line', '?')})"
                                print(f"    ✓ {function_name}: Read {lines_info}")
                            elif function_name == "find":
                                print(f"    ✓ {function_name}: Found {result.get('count', 0)} files")
                            elif function_name == "grep":
                                print(f"    ✓ {function_name}: Found {result.get('match_count', 0)} matches")
                            else:
                                print(f"    ✓ {function_name}: Success")
                        else:
                            # 出错 —— 显示错误信息
                            print(f"    ✗ {function_name}: {result.get('error', 'Unknown error')}")
                        
                        # 工具结果作为规范的 tool 消息加入（含错误）
                        tool_message = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result)
                        }
                        # 始终追加到本轮的 messages
                        messages.append(tool_message)
                        # 同时追加到历史，供下一轮使用
                        self.conversation_history.append(tool_message)
                        
                        # 工具返回错误时记录日志
                        if not result.get("success", True):
                            if self.verbose:
                                logger.warning(f"Tool {function_name} returned error: {result.get('error', 'Unknown error')}")
                
                elif message.content:
                    # 无工具调用 —— 视为最终答案
                    final_answer = message.content
                    # 始终追加到本轮的 messages
                    messages.append(message.model_dump())
                    # 同时追加到历史，供下一轮使用
                    self.conversation_history.append(message.model_dump())
                    if self.verbose:
                        logger.info("No tool calls in response - considering as final answer")
                    break
                
            except Exception as e:
                logger.error(f"Error in iteration {iteration}: {str(e)}")
                break
        
        # 计算最终指标
        self.metrics.total_time = time.time() - start_time
        self.metrics.iterations = iteration
        self.metrics.tool_calls = len(tool_calls)
        
        return {
            "success": final_answer is not None,
            "final_answer": final_answer,
            "iterations": iteration,
            "tool_calls": tool_calls,
            "metrics": self.metrics,
            "mode": self.mode.value
        }


def compare_implementations(api_key: str, task: str, root_dir: str = ".",
                            model: str = "kimi-k2.6") -> Dict[str, Any]:
    """
    对比不同的 KV cache 实现

    Args:
        api_key: Kimi 的 API key
        task: 要执行的任务
        root_dir: 文件操作的根目录
        model: 所有模式共用的模型

    Returns:
        对比结果
    """
    results = {}

    for mode in KVCacheMode:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing mode: {mode.value}")
        logger.info(f"{'='*60}")

        agent = KVCacheAgent(api_key=api_key, mode=mode, model=model, root_dir=root_dir, verbose=True)
        result = agent.execute_task(task)
        
        results[mode.value] = {
            "success": result["success"],
            "iterations": result["iterations"],
            "tool_calls": result["tool_calls"],
            "metrics": asdict(result["metrics"])
        }
        
        # 记录摘要
        metrics = result["metrics"]
        logger.info(f"\nMode: {mode.value}")
        logger.info(f"First TTFT: {metrics.ttft:.3f}s")
        
        # 记录 TTFT 变化
        if metrics.ttft_per_iteration:
            ttft_summary = ", ".join([f"{t:.3f}s" for t in metrics.ttft_per_iteration[:5]])
            if len(metrics.ttft_per_iteration) > 5:
                ttft_summary += f"... ({len(metrics.ttft_per_iteration)} total)"
            logger.info(f"TTFT per iteration: [{ttft_summary}]")
            
            # 计算首次到末次的 TTFT 改善幅度
            if len(metrics.ttft_per_iteration) > 1:
                improvement = (metrics.ttft_per_iteration[0] - metrics.ttft_per_iteration[-1]) / metrics.ttft_per_iteration[0] * 100
                logger.info(f"TTFT improvement: {improvement:.1f}% (first vs last)")
        
        logger.info(f"Total Time: {metrics.total_time:.3f}s")
        logger.info(f"Cached Tokens: {metrics.cached_tokens}")
        logger.info(f"Cache Hits: {metrics.cache_hits}")
        logger.info(f"Cache Misses: {metrics.cache_misses}")
        logger.info(f"Total Tokens: {metrics.prompt_tokens + metrics.completion_tokens}")
    
    return results
