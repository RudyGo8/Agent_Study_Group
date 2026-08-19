"""kv-cache 实验测试的 pytest 引导模块。"""

from pathlib import Path
import sys
import types


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
if str(EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(EXPERIMENT_ROOT))

try:
    import openai  # noqa: F401
except ImportError:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = object
    sys.modules.setdefault("openai", openai_stub)
