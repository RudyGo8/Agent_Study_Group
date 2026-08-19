"""
System-Hint 增强 Agent 的配置模块
"""

import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

from agentbook.providers import PROVIDERS, canonical_provider

load_dotenv()


@dataclass
class AgentConfig:
    """System-Hint Agent 的配置"""
    
    # API 配置
    api_key: Optional[str] = None
    provider: str = "kimi"
    model: Optional[str] = None
    
    # System hint 功能开关
    enable_timestamps: bool = True
    enable_tool_counter: bool = True
    enable_todo_list: bool = True
    enable_detailed_errors: bool = True
    enable_system_state: bool = True
    
    # 格式化选项
    timestamp_format: str = "%Y-%m-%d %H:%M:%S"
    simulate_time_delay: bool = False
    
    # 执行选项
    max_iterations: int = 20
    verbose: bool = False
    timeout: int = 30  # 命令执行的超时秒数
    
    @classmethod
    def from_env(cls) -> "AgentConfig":
        """从环境变量创建配置"""
        provider = canonical_provider(os.getenv("LLM_PROVIDER", "kimi"))
        return cls(
            # 提供商凭据与别名统一来自共享注册表。
            api_key=PROVIDERS.get(provider, PROVIDERS["kimi"]).api_key() or os.getenv("OPENROUTER_API_KEY"),
            provider=provider,
            model=os.getenv("LLM_MODEL"),
            enable_timestamps=os.getenv("ENABLE_TIMESTAMPS", "true").lower() == "true",
            enable_tool_counter=os.getenv("ENABLE_TOOL_COUNTER", "true").lower() == "true",
            enable_todo_list=os.getenv("ENABLE_TODO_LIST", "true").lower() == "true",
            enable_detailed_errors=os.getenv("ENABLE_DETAILED_ERRORS", "true").lower() == "true",
            enable_system_state=os.getenv("ENABLE_SYSTEM_STATE", "true").lower() == "true",
            timestamp_format=os.getenv("TIMESTAMP_FORMAT", "%Y-%m-%d %H:%M:%S"),
            simulate_time_delay=os.getenv("SIMULATE_TIME_DELAY", "false").lower() == "true",
            max_iterations=int(os.getenv("MAX_ITERATIONS", "20")),
            verbose=os.getenv("VERBOSE", "false").lower() == "true",
            timeout=int(os.getenv("COMMAND_TIMEOUT", "30"))
        )
    
    def validate(self) -> bool:
        """校验配置"""
        if not self.api_key:
            raise ValueError("API key is required. Set the selected provider's key or OPENROUTER_API_KEY fallback.")

        self.provider = canonical_provider(self.provider)
        if self.provider not in {"kimi", "moonshot", "dashscope"}:
            raise ValueError(f"Unsupported provider: {self.provider}")
        
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        
        if self.timeout < 1:
            raise ValueError("timeout must be at least 1 second")
        
        return True


# 默认配置预设
PRESETS = {
    "full": AgentConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True
    ),
    "minimal": AgentConfig(
        enable_timestamps=False,
        enable_tool_counter=False,
        enable_todo_list=False,
        enable_detailed_errors=False,
        enable_system_state=False
    ),
    "debug": AgentConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True,
        verbose=True
    ),
    "demo": AgentConfig(
        enable_timestamps=True,
        enable_tool_counter=True,
        enable_todo_list=True,
        enable_detailed_errors=True,
        enable_system_state=True,
        simulate_time_delay=True
    )
}


def get_config(preset: Optional[str] = None) -> AgentConfig:
    """
    从环境变量或预设获取配置
    
    参数:
        preset: 可选的预设名（'full'、'minimal'、'debug'、'demo'）
        
    返回:
        AgentConfig 实例
    """
    if preset and preset in PRESETS:
        config = PRESETS[preset]
        # 若环境变量中有 API Key 则覆盖
        config.api_key = os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        return config
    
    return AgentConfig.from_env()
