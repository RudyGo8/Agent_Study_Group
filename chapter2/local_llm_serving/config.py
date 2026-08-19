"""
vLLM 工具调用演示的配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 模型配置
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-0.6B")  # 可填 ModelScope 路径或 HuggingFace
MODEL_PATH = os.getenv("MODEL_PATH", None)  # 可选：本地模型路径
VLLM_PORT = int(os.getenv("VLLM_PORT", 8000))
VLLM_HOST = os.getenv("VLLM_HOST", "localhost")

# vLLM 服务端配置
VLLM_SERVER_CONFIG = {
    "model": MODEL_NAME,
    "port": VLLM_PORT,
    "host": VLLM_HOST,
    "enable_auto_tool_choice": True,
    "tool_call_parser": "hermes",
    "max_model_len": 8192,
    "gpu_memory_utilization": 0.9,
    "dtype": "auto",
    "enforce_eager": False,  # 遇到问题时可改为 True
}

# OpenAI 客户端配置（用于连接 vLLM）
OPENAI_API_BASE = f"http://{VLLM_HOST}:{VLLM_PORT}/v1"
OPENAI_API_KEY = "EMPTY"  # vLLM 不需要真实 key

# 工具配置
ENABLE_WEATHER_TOOL = True
ENABLE_CALCULATOR_TOOL = True
ENABLE_SEARCH_TOOL = True

# 日志
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = Path("logs") / "vllm_tool_demo.log"
