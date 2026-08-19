"""
上下文压缩基准测试模块。

在长上下文任务上系统评测摘要（Summary）、截断（Truncation）、关键句（Key-Sentence）
与观察过滤（Observation-Filtering）四种压缩策略。度量压缩率、首 token 延迟（TTFT）、
token 成本节省比例，以及下游问答的保留准确率。
"""

import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Tuple


def count_tokens(text: str) -> int:
    """估算一段文本的 token 数。

    优先使用 tiktoken，不可用时回退到基于字符/词数的可靠估算。
    """
    if not text:
        return 0
    try:
        import tiktoken
        try:
            encoding = tiktoken.encoding_for_model("gpt-4")
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        # 回退估算：约 4 字符/token 或约 0.75 词/token
        words = len(text.split())
        chars = len(text)
        return max(1, int((words * 1.3 + chars / 4) / 2))


@dataclass
class StrategyMetrics:
    """一种上下文压缩策略的性能指标。"""
    strategy: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float  # compressed_tokens / original_tokens
    ttft_ms: float            # 首 token 延迟（毫秒）
    token_cost_savings: float # 成本节省比例（0.0 到 1.0）
    qa_retention_accuracy: float # 下游问答准确率（0.0 到 1.0）

    def to_dict(self) -> Dict[str, Any]:
        """把指标转成标准字典表示。"""
        return {
            "strategy": self.strategy,
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "compression_ratio": self.compression_ratio,
            "ttft_ms": self.ttft_ms,
            "token_cost_savings": self.token_cost_savings,
            "qa_retention_accuracy": self.qa_retention_accuracy,
        }


class ContextCompressionBenchmark:
    """评测上下文压缩策略的基准测试框架。"""

    STRATEGIES = ["summary", "truncation", "key_sentence", "observation_filtering"]

    def __init__(
        self,
        base_ttft_ms: float = 50.0,
        per_token_ttft_ms: float = 0.05,
        token_cost_per_1k: float = 0.0015,
        target_max_tokens: int = 500,
    ):
        """初始化基准测试套件，性能参数可配置。"""
        self.base_ttft_ms = base_ttft_ms
        self.per_token_ttft_ms = per_token_ttft_ms
        self.token_cost_per_1k = token_cost_per_1k
        self.target_max_tokens = target_max_tokens

    def compress_summary(self, context: str, query: str = "") -> str:
        """摘要策略：把上下文浓缩为关键要点。"""
        if not context:
            return ""
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', context) if s.strip()]
        if not sentences:
            return context
        if len(sentences) <= 3:
            return context
        # 取开头、中间、结尾的句子组成简短摘要
        step = max(1, len(sentences) // 3)
        summary_sentences = [sentences[0]]
        if step < len(sentences):
            summary_sentences.append(sentences[step])
        if len(sentences) - 1 > step:
            summary_sentences.append(sentences[-1])
        return " ".join(summary_sentences)

    def compress_truncation(self, context: str, max_tokens: Optional[int] = None) -> str:
        """截断策略：按严格的 token 上限切分上下文。"""
        if not context:
            return ""
        limit = self.target_max_tokens if max_tokens is None else max_tokens
        if limit <= 0:
            return ""
        words = context.split()
        if not words:
            # 没有按空白分隔的词（如中文文本）：按字符数截断。
            # 一个 CJK 字符约折合 1-2 个 token，保守按 1:1 处理。
            return context[:limit]
        # 按 token 上限估算最大词数（约 0.75 词/token）
        max_words = max(1, int(limit * 0.75))
        truncated_words = words[:max_words]
        return " ".join(truncated_words)
    def compress_key_sentence(self, context: str, query: str = "") -> str:
        """关键句策略：保留与查询词匹配度高、相关性强的句子。"""
        if not context:
            return ""
        query = query or ""
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', context) if s.strip()]
        if not sentences:
            return context
        if not query:
            # 查询为空时，回退到按句长/位置打分
            scored = sorted(enumerate(sentences), key=lambda x: len(x[1]), reverse=True)
            top_indices = sorted([idx for idx, _ in scored[:max(1, len(sentences) // 2)]])
            return " ".join([sentences[i] for i in top_indices])

        query_terms = set(re.findall(r'\w+', query.lower()))
        scored_sentences = []
        for idx, sentence in enumerate(sentences):
            sentence_terms = set(re.findall(r'\w+', sentence.lower()))
            overlap = len(query_terms.intersection(sentence_terms))
            scored_sentences.append((overlap, idx, sentence))

        # 按重叠度降序，再按原始位置排序
        scored_sentences.sort(key=lambda x: (-x[0], x[1]))
        # 保留得分靠前的一半句子
        keep_count = max(1, math.ceil(len(sentences) * 0.5))
        selected = scored_sentences[:keep_count]
        # 把选中的句子按原上下文顺序排回
        selected.sort(key=lambda x: x[1])
        return " ".join([s[2] for s in selected])

    def compress_observation_filtering(self, context: str) -> str:
        """观察过滤策略：移除冗长的系统输出、日志、十六进制串和 JSON 数据块。"""
        if not context:
            return ""
        lines = context.splitlines()
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            # 过滤类 JSON 数据块、长十六进制哈希、trace 日志或重复的调试标记
            if (
                re.match(r'^\s*[\{\[\}\]].*$', stripped) or
                re.search(r'\b[0-9a-fA-F]{32,64}\b', stripped) or
                re.search(r'^\s*(DEBUG|TRACE|INFO|VERBOSE)\b', stripped, re.IGNORECASE) or
                re.search(r'^\s*<.*?>\s*$', stripped)
            ):
                continue
            filtered_lines.append(line)
        result = "\n".join(filtered_lines).strip()
        return result if result else context

    def compress(self, strategy: str, context: str, query: str = "") -> str:
        """对给定上下文字符串应用指定压缩策略。"""
        strat = strategy.lower().replace("-", "_")
        if strat == "summary":
            return self.compress_summary(context, query)
        elif strat == "truncation":
            return self.compress_truncation(context)
        elif strat in ("key_sentence", "keysentence"):
            return self.compress_key_sentence(context, query)
        elif strat in ("observation_filtering", "observationfiltering"):
            return self.compress_observation_filtering(context)
        else:
            raise ValueError(f"Unknown compression strategy: {strategy}")

    def evaluate_retention(self, compressed_text: str, task: Union[str, Dict[str, Any]]) -> Optional[float]:
        """评估压缩后上下文在下游问答中的保留准确率。"""
        compressed_text = compressed_text or ""
        task = task or ""
        query = task if isinstance(task, str) else (task.get("query", "") if isinstance(task, dict) else "")
        expected = task.get("expected_answer", "") if isinstance(task, dict) else ""
        if query is None:
            query = ""
        if expected is None:
            expected = ""
        # 只对照期望答案打分，不用查询词。
        # 若回退用查询词，得分会虚高：即使答案被压缩删掉，
        # 问题文本也往往还在。
        target_text = expected.strip()
        target_tokens = set(re.findall(r'\w+', target_text.lower()))

        if not target_tokens:
            # 没有期望答案可对照：无法评估保留率。
            return None
            
        compressed_tokens = set(re.findall(r'\w+', compressed_text.lower()))
        matched = target_tokens.intersection(compressed_tokens)
        
        # 计算召回准确率
        accuracy = len(matched) / len(target_tokens)
        return min(1.0, max(0.0, accuracy))

    def evaluate_strategy(
        self,
        strategy: str,
        contexts: List[str],
        tasks: List[Union[str, Dict[str, Any]]],
    ) -> StrategyMetrics:
        """在多组上下文与任务上评测单个压缩策略。"""
        total_orig_tokens = 0
        total_comp_tokens = 0
        total_retention_acc = 0.0
        retention_count = 0
        sample_count = 0

        start_time = time.perf_counter()

        for idx, ctx in enumerate(contexts):
            task = tasks[idx % len(tasks)] if tasks else ""
            if task is None:
                task = ""
            query = task if isinstance(task, str) else (task.get("query", "") if isinstance(task, dict) else "")
            query = query or ""
            orig_tokens = count_tokens(ctx)
            compressed_ctx = self.compress(strategy, ctx, query=query)
            comp_tokens = count_tokens(compressed_ctx)

            retention_acc = self.evaluate_retention(compressed_ctx, task)

            total_orig_tokens += orig_tokens
            total_comp_tokens += comp_tokens
            if retention_acc is not None:
                total_retention_acc += retention_acc
                retention_count += 1
            sample_count += 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        avg_orig_tokens = total_orig_tokens / max(1, sample_count)
        avg_comp_tokens = total_comp_tokens / max(1, sample_count)
        avg_retention_acc = total_retention_acc / max(1, retention_count)

        if avg_orig_tokens == 0:
            ratio = 0.0
            savings = 0.0
        else:
            ratio = avg_comp_tokens / avg_orig_tokens
            savings = max(0.0, 1.0 - ratio)

        # 模拟 TTFT：基础 TTFT + 处理耗时 + 按压缩后 token 数估算的 prefill 延迟
        simulated_ttft = self.base_ttft_ms + (avg_comp_tokens * self.per_token_ttft_ms) + (elapsed_ms / max(1, sample_count))

        # 规范化策略名
        strat_key = strategy.lower().replace("-", "_")

        return StrategyMetrics(
            strategy=strat_key,
            original_tokens=int(avg_orig_tokens),
            compressed_tokens=int(avg_comp_tokens),
            compression_ratio=round(ratio, 4),
            ttft_ms=round(simulated_ttft, 2),
            token_cost_savings=round(savings, 4),
            qa_retention_accuracy=round(avg_retention_acc, 4),
        )

    def run_benchmark(
        self,
        contexts: Union[str, List[Union[str, Dict[str, Any]]]],
        tasks: Union[str, List[Union[str, Dict[str, Any]]]],
    ) -> Dict[str, Any]:
        """对所有压缩策略做系统性基准测试。

        参数:
            contexts: 单个上下文字符串、字典，或二者组成的列表。
            tasks: 单个任务/查询字符串、字典，或二者组成的列表。

        返回:
            以策略名为键、性能指标字典为值的对比指标字典。
        """
        # 把上下文统一成文本字符串列表
        if isinstance(contexts, (str, dict)):
            raw_contexts = [contexts]
        else:
            raw_contexts = list(contexts)

        normalized_contexts = []
        for c in raw_contexts:
            if isinstance(c, str):
                normalized_contexts.append(c)
            elif isinstance(c, dict):
                content = c.get("content")
                if content is None:
                    content = c.get("text")
                # 用提取到的 content，找不到就置空字符串。
                # 若回退到 str(c)，会把原始字典的 repr 当成上下文
                # 文本，得出无意义的基准指标。
                normalized_contexts.append(content if content is not None else "")
            else:
                normalized_contexts.append(str(c))

        # 把任务统一成查询/任务对象列表
        if isinstance(tasks, (str, dict)):
            normalized_tasks = [tasks]
        else:
            normalized_tasks = list(tasks)

        results: Dict[str, Any] = {}

        for strategy in self.STRATEGIES:
            metrics = self.evaluate_strategy(strategy, normalized_contexts, normalized_tasks)
            metrics_dict = metrics.to_dict()
            display_name = {
                "summary": "Summary",
                "truncation": "Truncation",
                "key_sentence": "Key-Sentence",
                "observation_filtering": "Observation-Filtering",
            }.get(strategy, strategy)
            metrics_dict["display_name"] = display_name
            results[strategy] = metrics_dict

        return results


def run_benchmark(
    contexts: Union[str, List[Union[str, Dict[str, Any]]]],
    tasks: Union[str, List[Union[str, Dict[str, Any]]]],
) -> Dict[str, Any]:
    """执行压缩基准测试的模块级入口。

    参数:
        contexts: 输入上下文（字符串或字典）。
        tasks: 下游问答任务或查询。

    返回:
        每种压缩策略的对比性能指标字典。
    """
    benchmark = ContextCompressionBenchmark()
    return benchmark.run_benchmark(contexts, tasks)
