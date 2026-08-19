"""
注意力可视化配置
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 模型配置
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-0.6B")
MODEL_PATH = os.getenv("MODEL_PATH", None)  # 可选的本地模型路径

# 设备配置
DEVICE = os.getenv("DEVICE", "auto")  # 可取 auto、cuda、mps 或 cpu

# 注意力配置
ATTENTION_LAYER_INDEX = int(os.getenv("ATTENTION_LAYER_INDEX", -1))  # -1 表示最后一层
TRACK_ALL_LAYERS = os.getenv("TRACK_ALL_LAYERS", "false").lower() == "true"

# 生成配置
DEFAULT_MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", 100))
DEFAULT_TEMPERATURE = float(os.getenv("TEMPERATURE", 0.7))
DEFAULT_TOP_P = float(os.getenv("TOP_P", 0.9))
DEFAULT_REPETITION_PENALTY = float(os.getenv("REPETITION_PENALTY", 1.1))

# 可视化配置
VIZ_OUTPUT_DIR = Path(os.getenv("VIZ_OUTPUT_DIR", "visualizations"))
VIZ_FORMATS = os.getenv("VIZ_FORMATS", "heatmap,flow,summary").split(",")
VIZ_COLORMAP = os.getenv("VIZ_COLORMAP", "viridis")
VIZ_FIGSIZE = tuple(map(int, os.getenv("VIZ_FIGSIZE", "14,10").split(",")))
VIZ_DPI = int(os.getenv("VIZ_DPI", 150))

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = Path(os.getenv("LOG_FILE", "attention_viz.log"))

# 输出配置
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", "results"))
RESULTS_DIR.mkdir(exist_ok=True)
VIZ_OUTPUT_DIR.mkdir(exist_ok=True)

# 交互模式配置
INTERACTIVE_MODE = os.getenv("INTERACTIVE_MODE", "true").lower() == "true"
AUTO_VISUALIZE = os.getenv("AUTO_VISUALIZE", "true").lower() == "true"

# 演示配置
DEMO_PROMPTS = [
    "What is the capital of France?",
    "Explain photosynthesis in simple terms",
    "Write a haiku about artificial intelligence",
    "List three benefits of exercise",
    "What is 25 * 4 + 10?",
]

# 不同模式的系统提示词
SYSTEM_PROMPTS = {
    "default": "You are a helpful AI assistant.",
    "technical": "You are a technical expert AI assistant. Provide detailed and accurate technical information.",
    "creative": "You are a creative AI assistant. Be imaginative and original in your responses.",
    "concise": "You are a concise AI assistant. Provide brief, clear answers without unnecessary elaboration.",
}
