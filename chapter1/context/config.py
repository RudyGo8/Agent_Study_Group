"""
上下文感知 Agent 的配置模块
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 提供商解析位于共享的 agentbook 包中，保证各章一致；
# 见 agentbook/providers.py。下面的兜底保证在未安装 agentbook 的
# 检出目录里本实验仍可运行。
try:
    from agentbook.providers import (
        PROVIDERS,
        SUPPORTED_PROVIDERS,
        canonical_provider,
        resolve_backend,
    )
except ImportError:  # pragma: no cover - 仅在未安装该包时才会走到
    import sys as _sys

    _sys.path.insert(
        0, str(__import__("pathlib").Path(__file__).resolve().parents[2])
    )
    from agentbook.providers import (
        PROVIDERS,
        SUPPORTED_PROVIDERS,
        canonical_provider,
        resolve_backend,
    )

# 本模块同时向 main.py 等入口再导出注册表符号（连同上面的
# 未安装兜底），所以它们在本文件内没有其他使用处。
__all__ = [
    "PROVIDERS",
    "SUPPORTED_PROVIDERS",
    "canonical_provider",
    "resolve_backend",
    "Config",
]


class Config:
    """Agent 的配置项"""

    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "doubao").lower()
    MODEL_NAME: str = os.getenv("MODEL_NAME", "")  # 未指定时用提供商默认模型
    MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "10"))

    @classmethod
    def get_default_model(cls, provider: str = None) -> str:
        """
        获取指定提供商的默认模型

        参数:
            provider: 提供商名称（默认为 LLM_PROVIDER）

        返回:
            该提供商的默认模型名
        """
        provider = provider or cls.LLM_PROVIDER

        if cls.MODEL_NAME:
            return cls.MODEL_NAME

        try:
            return PROVIDERS[canonical_provider(provider)].default_model
        except KeyError:
            return ""

