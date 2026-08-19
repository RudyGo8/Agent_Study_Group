"""
上下文感知 AI Agent（带工具调用）
一个使用多提供商 LLM 的 Agent，配备文档解析、货币换算和计算器等工具。
通过消融实验（ablation study）演示上下文各组件的重要性。
"""

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from io import BytesIO
from typing import Any, Dict, List, Optional

import PyPDF2
import requests
from openai import OpenAI

from config import Config, resolve_backend

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _reasoning_safe_temperature(model, requested=1.0):
    """思考型模型（Kimi K3、GPT-5 等）只接受 temperature=1。
    对这类模型返回 1；否则返回请求值，保持非思考型提供商
    （Doubao、DeepSeek、旧版 Moonshot）行为不变。"""
    m = str(model or "").lower().replace("/", "-")
    return 1 if ("kimi-k3" in m or "gpt-5" in m) else requested


# 示例汇率（教学用固定值；生产环境应使用实时 API）
EXCHANGE_RATES = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.79,
    "JPY": 149.50,
    "CNY": 7.24,
    "CAD": 1.36,
    "AUD": 1.53,
    "CHF": 0.88,
    "INR": 83.12,
    "SGD": 1.34,
}

# 模型常把货币写成符号或前缀形式（"US$"、"€ 500"、"$1,000.00"）。
# 金额清洗与货币代码归一化共用这一张表。
_CURRENCY_SYMBOLS = {
    "$": "USD",
    "US$": "USD",
    "U.S.$": "USD",
    "USD$": "USD",
    "S$": "SGD",
    "SG$": "SGD",
    "SGD$": "SGD",
    "A$": "AUD",
    "AU$": "AUD",
    "AUD$": "AUD",
    "C$": "CAD",
    "CA$": "CAD",
    "CAD$": "CAD",
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
}


class ContextMode(Enum):
    """消融实验用的各种上下文模式"""

    FULL = "full"  # 完整上下文，包含全部组件
    NO_HISTORY = "no_history"  # 无历史工具调用记录
    NO_REASONING = "no_reasoning"  # 无思考过程（reasoning）
    NO_TOOL_CALLS = "no_tool_calls"  # 无工具调用命令
    NO_TOOL_RESULTS = "no_tool_results"  # 无工具执行结果


def _model_to_dict(obj: Any) -> Dict[str, Any]:
    """SDK 响应对象转字典（兼容 pydantic v1/v2 形态）。"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return {"raw_response": str(obj)}


# 提供给模型的工具描述（OpenAI function-calling 格式），内容是静态的
TOOLS_DESCRIPTION = [
    {
        "type": "function",
        "function": {
            "name": "parse_pdf",
            "description": "Download and parse a PDF document from a URL or a file path to extract text content",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL or file path of the PDF document to parse",
                    }
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "convert_currency",
            "description": "Convert an amount from one currency to another using current exchange rates",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "The amount to convert",
                    },
                    "from_currency": {
                        "type": "string",
                        "description": "The source currency code (e.g., USD, EUR)",
                    },
                    "to_currency": {
                        "type": "string",
                        "description": "The target currency code (e.g., USD, EUR)",
                    },
                },
                "required": ["amount", "from_currency", "to_currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a simple mathematical expression",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The mathematical expression to evaluate (e.g., '2 + 2 * 3')",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "code_interpreter",
            "description": "Execute Python code for complex calculations, data processing, and computing totals. Use this for tasks like: summing lists of values, calculating percentages, aggregating financial data, performing multi-step calculations, or any computation requiring variables and intermediate steps.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute. Can use variables, loops, and mathematical operations. Example: 'amounts = [2500000, 2278481, 2541806, 2282609, 2388060]; total = sum(amounts); print(f\"Total: ${total:,.2f}\")'",
                    }
                },
                "required": ["code"],
            },
        },
    },
]


@dataclass
class ToolCall:
    """表示一次工具调用"""

    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class AgentTrajectory:
    """记录 Agent 的执行轨迹"""

    reasoning_steps: List[str] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    # 每一轮真实模型交互的精确、无凭据请求/响应证据。
    # 刻意作为轨迹的一部分保存：实验 1-1 关心的是"模型在决策时能看到
    # 什么"，事后重建请求不算合格证据。
    api_turns: List[Dict[str, Any]] = field(default_factory=list)
    context_mode: ContextMode = ContextMode.FULL


class ToolRegistry:
    """可用工具的注册表"""

    @staticmethod
    def parse_pdf(url: str) -> Dict[str, Any]:
        """
        从 URL 或本地文件下载并解析 PDF

        参数:
            url: 待解析 PDF 的 URL 或文件路径

        返回:
            包含解析出的文本和元数据的字典
        """
        try:
            if "://" in url and not url.startswith("file://"):
                # 远程 URL，下载它
                logger.info(f"Downloading PDF from {url}")
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                pdf_content = response.content
            else:
                # 本地文件路径（file:// 前缀剥掉后直接读取）
                file_path = url.removeprefix("file://")
                logger.info(f"Reading local PDF from {file_path}")
                with open(file_path, "rb") as f:
                    pdf_content = f.read()

            # 解析 PDF 内容
            pdf_file = BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)

            text_content = []
            for page_num, page in enumerate(pdf_reader.pages, 1):
                text = page.extract_text()
                text_content.append({"page": page_num, "text": text})

            result = {
                "url": url,
                "num_pages": len(pdf_reader.pages),
                "content": text_content,
                "metadata": (
                    pdf_reader.metadata if hasattr(pdf_reader, "metadata") else {}
                ),
            }

            logger.info(f"Successfully parsed PDF with {len(pdf_reader.pages)} pages")
            return result

        except Exception as e:
            logger.error(f"Error parsing PDF: {str(e)}")
            return {"error": str(e)}

    @staticmethod
    def convert_currency(
        amount: float, from_currency: str, to_currency: str
    ) -> Dict[str, Any]:
        """
        使用汇率换算货币

        参数:
            amount: 待换算金额
            from_currency: 源货币代码（如 'USD'）
            to_currency: 目标货币代码（如 'EUR'）

        返回:
            包含换算结果的字典
        """
        try:
            if isinstance(amount, str):
                clean_amt = amount.replace(",", "").strip()
                for sym in sorted(_CURRENCY_SYMBOLS, key=len, reverse=True):
                    clean_amt = clean_amt.replace(sym, "")
                amount = float(clean_amt.strip())
            else:
                amount = float(amount)

            def _normalize_code(code: str) -> str:
                if not isinstance(code, str):
                    return str(code or "")
                c = code.strip().upper()
                if c in _CURRENCY_SYMBOLS:
                    return _CURRENCY_SYMBOLS[c]
                if c.endswith("$"):
                    prefix = c[:-1].strip()
                    if prefix in EXCHANGE_RATES:
                        return prefix
                    if prefix in ("US", "U.S."):
                        return "USD"
                    if prefix in ("AU", "A"):
                        return "AUD"
                    if prefix in ("CA", "C"):
                        return "CAD"
                return c

            from_currency = _normalize_code(from_currency)
            to_currency = _normalize_code(to_currency)

            logger.info(f"Converting {amount} {from_currency} to {to_currency}")

            if from_currency not in EXCHANGE_RATES or to_currency not in EXCHANGE_RATES:
                return {
                    "error": f"Unsupported currency: {from_currency} or {to_currency}"
                }

            # 先换算成 USD，再换算成目标货币
            usd_amount = amount / EXCHANGE_RATES[from_currency]
            converted_amount = usd_amount * EXCHANGE_RATES[to_currency]

            result = {
                "original_amount": amount,
                "from_currency": from_currency,
                "to_currency": to_currency,
                "converted_amount": round(converted_amount, 2),
                "exchange_rate": round(
                    EXCHANGE_RATES[to_currency] / EXCHANGE_RATES[from_currency], 4
                ),
                "timestamp": datetime.now().isoformat(),
            }

            logger.info(
                f"Conversion result: {result['converted_amount']} {to_currency}"
            )
            return result

        except Exception as e:
            logger.error(f"Error converting currency: {str(e)}")
            return {"error": str(e)}

    @staticmethod
    def calculate(expression: str) -> Dict[str, Any]:
        """
        求一个数学表达式的值

        参数:
            expression: 待求值的数学表达式

        返回:
            包含计算结果的字典
        """
        try:
            logger.info(f"Calculating: {expression}")

            # 净化表达式 —— 只允许安全的数学运算
            allowed_names = {
                k: v for k, v in math.__dict__.items() if not k.startswith("__")
            }
            allowed_names.update({"abs": abs, "round": round, "min": min, "max": max})

            # 为清晰起见替换常见写法
            expression = expression.replace("^", "**")

            # 求值
            result = eval(expression, {"__builtins__": {}}, allowed_names)

            return {
                "expression": expression,
                "result": result,
                "type": type(result).__name__,
            }

        except Exception as e:
            logger.error(f"Error calculating expression: {str(e)}")
            return {"error": str(e)}

    @staticmethod
    def code_interpreter(code: str) -> Dict[str, Any]:
        """
        执行 Python 代码，用于复杂计算与数据处理

        参数:
            code: 待执行的 Python 代码

        返回:
            包含执行结果和输出的字典
        """
        try:
            logger.info(f"Executing Python code: {code[:100]}...")

            # 创建一个只含安全内置函数的受限命名空间
            safe_namespace = {
                "__builtins__": {
                    "abs": abs,
                    "all": all,
                    "any": any,
                    "sum": sum,
                    "min": min,
                    "max": max,
                    "round": round,
                    "len": len,
                    "list": list,
                    "dict": dict,
                    "set": set,
                    "tuple": tuple,
                    "enumerate": enumerate,
                    "zip": zip,
                    "map": map,
                    "filter": filter,
                    "sorted": sorted,
                    "reversed": reversed,
                    "range": range,
                    "int": int,
                    "float": float,
                    "str": str,
                    "bool": bool,
                    "print": print,
                }
            }

            # 加入 math 模块
            safe_namespace["math"] = math

            # 捕获 print 输出
            import contextlib
            import io

            output_buffer = io.StringIO()

            with contextlib.redirect_stdout(output_buffer):
                # 执行代码
                exec(code, safe_namespace)

            # 获取打印输出
            printed_output = output_buffer.getvalue()

            # 尝试提取赋值给 'result' 变量的结果
            result = safe_namespace.get("result", None)

            # 再检查常见变量名
            if result is None:
                for var_name in ["total", "sum", "output", "answer", "final"]:
                    if var_name in safe_namespace:
                        result = safe_namespace[var_name]
                        break

            # 收集所有已定义变量（排除内置对象和模块）
            variables = {
                k: v
                for k, v in safe_namespace.items()
                if not k.startswith("__") and k not in ["math"] and not callable(v)
            }

            return {
                "code": code,
                "result": result,
                "output": printed_output if printed_output else None,
                "variables": variables,
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error executing code: {str(e)}")
            return {"code": code, "error": str(e), "success": False}


class ContextAwareAgent:
    """
    支持可配置 LLM 提供商与上下文模式的 AI Agent（用于消融实验）
    """

    def __init__(
        self,
        api_key: str,
        context_mode: ContextMode = ContextMode.FULL,
        provider: str = "siliconflow",
        model: Optional[str] = None,
        verbose: bool = True,
    ):
        """
        初始化 Agent

        参数:
            api_key: LLM 提供商的 API Key
            context_mode: 消融实验的上下文模式
            provider: 任意注册在 ``agentbook.providers`` 的提供商（例如
                ``dashscope``/``qwen``、``siliconflow``、``doubao``、
                ``kimi``、``deepseek`` 或 ``openrouter``）
            model: 可选的模型覆盖
            verbose: 为 True 时记录完整 HTTP 请求与响应（默认: True）
        """
        self.provider = provider.lower()
        self.verbose = verbose

        # Base URL、默认模型和 Key 查找都放在共享注册表
        # （agentbook/providers.py）里，在那里加一个提供商即可在此使用，
        # 无需改动本文件。resolve_backend 还会应用 OpenRouter 通用兜底：
        # 当提供商自己的 Key 缺失但 OPENROUTER_API_KEY 已设置时，请求
        # 会经由 OpenRouter 发出并映射模型 id。提供商 Key 存在时行为不变。
        backend = resolve_backend(self.provider, model=model, api_key=api_key)
        resolved_key = backend.api_key
        resolved_base_url = backend.base_url
        self.model = backend.model
        self.using_openrouter = backend.using_openrouter
        if self.using_openrouter:
            logger.info(
                f"{self.provider} API key not set; routing via OpenRouter "
                f"(model: {self.model})"
            )
        self.client = OpenAI(api_key=resolved_key, base_url=resolved_base_url)
        self.base_url = resolved_base_url

        self.context_mode = context_mode
        self.trajectory = AgentTrajectory(context_mode=context_mode)
        self.tools = ToolRegistry()

        # 初始化对话历史
        self.conversation_history = []
        self._init_system_prompt()

        logger.info(
            f"Agent initialized with provider: {self.provider}, model: {self.model}, context mode: {context_mode.value}, verbose: {self.verbose}"
        )

    def _init_system_prompt(self):
        """初始化对话的系统提示词"""
        self.conversation_history = [
            {
                "role": "system",
                "content": """You are an intelligent assistant with access to tools.

Your task is to solve the given problems using the available tools. Think step by step and use tools as needed.

Important: When you have gathered all necessary information and computed the final answer, clearly state "FINAL ANSWER:" followed by your answer.""",
            }
        ]

    def _prepare_assistant_message(self, message) -> Dict[str, Any]:
        """
        准备要加入消息列表的 assistant 消息，
        在 NO_REASONING 模式下过滤掉 reasoning_content

        参数:
            message: assistant 消息对象

        返回:
            消息的字典表示
        """
        msg_dict = _model_to_dict(message)

        # NO_REASONING 模式下移除 reasoning_content
        if (
            self.context_mode == ContextMode.NO_REASONING
            and "reasoning_content" in msg_dict
        ):
            msg_dict.pop("reasoning_content")

        return msg_dict

    @staticmethod
    def _reasoning_content(message) -> Optional[str]:
        """返回提供商的思考文本，不假设某一种 SDK 形态。"""
        value = getattr(message, "reasoning_content", None)
        if value:
            return str(value)
        extra = getattr(message, "model_extra", None) or {}
        value = extra.get("reasoning_content") or extra.get("reasoning")
        if isinstance(value, dict):
            value = value.get("content") or value.get("text")
        return str(value) if value else None

    @staticmethod
    def _json_snapshot(value: Any) -> Any:
        """把 API 证据对象与后续的内存修改隔离开（深拷贝快照）。"""
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))

    def _log_request_response(
        self, request_data: Dict[str, Any], response_dict: Dict[str, Any], iteration: int
    ):
        """
        verbose 模式下记录完整的请求与响应

        参数:
            request_data: 发送给 API 的请求负载
            response_dict: 已转换为字典的响应
            iteration: 当前迭代轮次
        """
        if not self.verbose:
            return

        if request_data:
            print("\n" + "=" * 80)
            print(f"📤 ITERATION {iteration} - FULL REQUEST JSON:")
            print("-" * 80)
            print(json.dumps(request_data, indent=2, ensure_ascii=False))

        if response_dict:
            print("\n" + "=" * 80)
            print(f"📥 ITERATION {iteration} - FULL RESPONSE:")
            print("-" * 80)
            print(json.dumps(response_dict, indent=2, ensure_ascii=False))
            print("=" * 80 + "\n")

    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        执行一个工具并返回结果

        参数:
            tool_name: 要执行的工具名
            arguments: 工具参数

        返回:
            工具执行结果
        """
        tool_map = {
            "parse_pdf": self.tools.parse_pdf,
            "convert_currency": self.tools.convert_currency,
            "calculate": self.tools.calculate,
            "code_interpreter": self.tools.code_interpreter,
        }

        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}"}

        return tool_map[tool_name](**arguments)

    def _prepare_messages_for_api(self) -> List[Dict[str, Any]]:
        """
        构建本轮真正发送给模型的消息列表，在此应用 NO_HISTORY 消融。

        除 NO_HISTORY 外的所有模式都原样返回完整对话历史（累积的轨迹）。
        NO_HISTORY 模式下，请求只包含静态系统提示词和当前用户任务；
        之前轮次的任何 assistant 决策、工具调用或工具结果都不保留。
        这就是实验 1-1 的字面消融：模型每次推理都从头开始任务，因此
        倾向于反复发出相同的第一个动作。单步滑动窗口仍然算历史，会让
        正文描述的实验实质变窄，所以不采用。

        返回:
            本轮要发送给模型的消息列表。
        """
        messages = self.conversation_history
        if self.context_mode != ContextMode.NO_HISTORY:
            return messages

        # 系统提示词始终保留，作为静态前缀。
        windowed = [m for m in messages if m.get("role") == "system"]

        # 锚定最近一条用户任务。其后的一切都不保留：那些消息正是
        # 要被消融掉的"上一轮历史"。
        user_indices = [i for i, m in enumerate(messages) if m.get("role") == "user"]
        if not user_indices:
            return windowed
        last_user_idx = user_indices[-1]
        windowed.append(messages[last_user_idx])
        return windowed

    @staticmethod
    def _extract_final_answer(content: str) -> Optional[str]:
        """若存在 FINAL ANSWER: 则提取其后的文本；否则返回 None。"""
        if not content or "FINAL ANSWER:" not in content:
            return None
        return content.split("FINAL ANSWER:", 1)[1].strip()

    def execute_task(
        self, task: str, max_iterations: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        使用可用工具执行一个任务（ReAct 循环）。

        停止条件：
          1. 模型给出纯文本回复（没有 tool_calls）—— 对话性质或任务完成，
             包括"hi"这类省略 FINAL ANSWER: 标记的普通回复；或
          2. 达到 max_iterations（工具调用循环的安全上限，例如
             no_tool_results 消融会触发）。

        参数:
            task: 要执行的任务
            max_iterations: 最大 ReAct 步数（默认: Config.MAX_ITERATIONS）。
                这是安全上限，不是目标轮数。

        返回:
            任务执行结果

        结果语义:
          - ``completed`` 表示循环收到了非空的终止文本响应。
            它不保证任务本身做对了。
          - ``task_success`` 在这里为 ``None``，因为对错是任务相关的，
            无法从任意自然语言提示推断。有评分标准的调用方应基于
            最终答案和轨迹自行计算。
          - ``success`` 保留为 ``completed`` 的向后兼容别名。
            新代码应使用 ``completed`` 或任务专属的 ``task_success``。
        """
        if max_iterations is None:
            max_iterations = Config.MAX_ITERATIONS

        # 把用户消息加入对话历史
        self.conversation_history.append({"role": "user", "content": task})

        # 直接使用对话历史（无需复制）
        messages = self.conversation_history

        iteration = 0
        final_answer = None

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Iteration {iteration}/{max_iterations}")

            try:
                # 构建真正发送给模型的消息列表。除 NO_HISTORY 外的
                # 所有模式都等于完整轨迹；NO_HISTORY 则只保留静态
                # 系统提示词和当前任务。
                api_messages = self._prepare_messages_for_api()

                # request_data 是发给模型的请求本体（也是证据快照的来源）；
                # create_kwargs 只是在它之上加网络层参数。
                request_data = {
                    "model": self.model,
                    "messages": api_messages,
                    "temperature": _reasoning_safe_temperature(self.model, 0.3),
                    "max_tokens": 8192,
                }
                if self.context_mode != ContextMode.NO_TOOL_CALLS:
                    request_data["tools"] = TOOLS_DESCRIPTION
                    request_data["tool_choice"] = "auto"

                create_kwargs = dict(request_data, timeout=180)
                # DeepSeek V4：开启 thinking，让 no_reasoning 消融能拿到
                # reasoning_content（与 Doubao/Kimi 的 thinking 默认值对齐）。
                # 经 OpenRouter 转发时跳过，因为那边未必接受相同的
                # extra body 结构。
                if self.provider == "deepseek" and not self.using_openrouter:
                    create_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                    request_data["thinking"] = {"type": "enabled"}

                logger.info(f"Sending request to {self.provider} API")

                # 带工具调用模型
                response = self.client.chat.completions.create(**create_kwargs)

                response_dict = _model_to_dict(response)
                self.trajectory.api_turns.append(
                    {
                        "iteration": iteration,
                        "provider": self.provider,
                        "resolved_model": self.model,
                        "base_url": self.base_url,
                        "using_openrouter": self.using_openrouter,
                        "request": self._json_snapshot(request_data),
                        "response": self._json_snapshot(response_dict),
                    }
                )

                # verbose 时记录请求与响应（内部自判 verbose）
                self._log_request_response(request_data, response_dict, iteration)

                message = response.choices[0].message
                has_tool_calls = bool(getattr(message, "tool_calls", None))
                reasoning_content = self._reasoning_content(message)
                if reasoning_content:
                    self.trajectory.reasoning_steps.append(reasoning_content)

                # --- 终止路径：无工具调用的文本回复 ---
                # 普通闲聊轮次（"hi" -> "Hello!"）或没有 FINAL ANSWER:
                # 标记的任务回答都必须结束 ReAct 循环。此前只有
                # "FINAL ANSWER:" 才会跳出循环，导致普通回复被反复
                # 重发至 max_iterations（浪费 API 调用）。
                if not has_tool_calls:
                    assistant_msg = self._prepare_assistant_message(message)
                    messages.append(assistant_msg)
                    content = (message.content or "").strip()
                    if content:
                        marked = self._extract_final_answer(content)
                        final_answer = marked if marked is not None else content
                        logger.info(
                            "Terminal text response (no tool calls); "
                            f"stopping after iteration {iteration}"
                        )
                    else:
                        logger.warning(
                            "Empty model response with no tool calls; "
                            "stopping to avoid burning remaining iterations"
                        )
                    break

                # --- 继续路径：模型请求执行工具 ---
                assistant_msg = self._prepare_assistant_message(message)
                messages.append(assistant_msg)
                for tool_call in message.tool_calls:
                    function_name = tool_call.function.name
                    raw_args = tool_call.function.arguments or "{}"
                    try:
                        function_args = json.loads(raw_args)
                    except json.JSONDecodeError as exc:
                        # 工具参数 JSON 非法时保住这一轮，不让任务中断。
                        err = (
                            f"Invalid tool arguments (not valid JSON): {exc}. "
                            f"Raw arguments: {raw_args[:500]}"
                        )
                        logger.warning(err)
                        self.trajectory.tool_calls.append(
                            ToolCall(
                                tool_name=function_name,
                                arguments={},
                                result={"error": err},
                            )
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({"error": err}),
                            }
                        )
                        continue

                    logger.info(
                        f"Executing tool: {function_name} with args: {function_args}"
                    )

                    result = self._execute_tool(function_name, function_args)

                    tool_call_record = ToolCall(
                        tool_name=function_name, arguments=function_args, result=result
                    )
                    self.trajectory.tool_calls.append(tool_call_record)

                    if self.context_mode != ContextMode.NO_TOOL_RESULTS:
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            # default=str: code_interpreter 在 `variables` 里
                            # 返回原始命名空间，可能含集合、字典视图等
                            # json 编不了的对象 —— 不能因此中断整个任务。
                            "content": json.dumps(result, default=str),
                        }
                    else:
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": "[Tool result hidden due to context mode]",
                        }
                    messages.append(tool_msg)

                # 若同一轮还标注了 FINAL ANSWER:（带工具时少见），
                # 仍优先在记录完工具后提取它。
                if message.content and "FINAL ANSWER:" in message.content:
                    final_answer = self._extract_final_answer(message.content)
                    logger.info(
                        f"Final answer found alongside tool calls: {final_answer}"
                    )
                    break

                # 注意：我们不再修改系统提示词。
                # 上下文已经通过工具历史构建进对话中

            except Exception as e:
                logger.error(f"Error during task execution: {str(e)}")
                self.trajectory.api_turns.append(
                    {
                        "iteration": iteration,
                        "provider": self.provider,
                        "resolved_model": self.model,
                        "base_url": self.base_url,
                        "using_openrouter": self.using_openrouter,
                        "error": {"class": type(e).__name__, "message": str(e)},
                    }
                )
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    error = "Request timed out. The model is taking too long to respond. Try a simpler task or different provider."
                else:
                    error = str(e)
                return {
                    "error": error,
                    "trajectory": self.trajectory,
                    "iterations": iteration,
                    "completed": False,
                    "task_success": False,
                    "success": False,
                }
        completed = bool(final_answer and str(final_answer).strip())
        return {
            "final_answer": final_answer,
            "trajectory": self.trajectory,
            "iterations": iteration,
            "completed": completed,
            "task_success": None,
            # 向后兼容别名。这是"收到终止响应"的状态，不是对错判断。
            "success": completed,
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "using_openrouter": self.using_openrouter,
        }

    def reset(self):
        """重置 Agent 的轨迹和对话历史"""
        self.trajectory = AgentTrajectory(context_mode=self.context_mode)
        self._init_system_prompt()  # 用系统提示词重新初始化对话
        logger.info("Agent trajectory and conversation history reset")

    def process(self, query: str, max_iterations: Optional[int] = None) -> str:
        """
        处理一个查询并以字符串形式返回最终答案

        参数:
            query: 要处理的查询
            max_iterations: 最大 ReAct 步数（默认取自 Config）

        返回:
            字符串形式的最终答案
        """
        result = self.execute_task(query, max_iterations)
        if result.get("final_answer"):
            return result["final_answer"]
        elif result.get("error"):
            return f"Error: {result['error']}"
        else:
            return "No answer found"
