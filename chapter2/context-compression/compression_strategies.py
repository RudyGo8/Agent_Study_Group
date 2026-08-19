"""
实验所用的上下文压缩策略
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from openai import OpenAI
import tiktoken
from config import Config


def _reasoning_safe_temperature(model, requested=1.0):
    """思考型模型（Kimi K3、GPT-5 等）只接受 temperature=1。
    对这类模型返回 1；否则返回请求值，保持非思考型提供商
    （Doubao、DeepSeek、旧版 Moonshot）行为不变。"""
    m = str(model or "").lower().replace("/", "-")
    return 1 if ("kimi-k3" in m or "gpt-5" in m) else requested


def _reasoning_safe_max_tokens(model, requested, reasoning_budget=2048):
    """思考型模型（Kimi K3、GPT-5 等）在输出可见答案*之前*就会把
    max_tokens 预算的一部分花在 reasoning_content 上。如果只传摘要
    预算（如 300-500），思考过程会挤占它，摘要会被截断甚至为空。
    给思考型模型额外留出余量，保证请求的输出预算完整留给摘要本身；
    非思考型模型行为不变。"""
    m = str(model or "").lower().replace("/", "-")
    if "kimi-k3" in m or "gpt-5" in m:
        return requested + reasoning_budget
    return requested

# 配置日志
logging.basicConfig(level=logging.INFO, format=Config.LOG_FORMAT)
logger = logging.getLogger(__name__)


class CompressionStrategy(Enum):
    """各种上下文压缩策略"""
    NO_COMPRESSION = "no_compression"
    NON_CONTEXT_AWARE_INDIVIDUAL = "non_context_aware_individual_summary"  # 逐页分别摘要后拼接
    NON_CONTEXT_AWARE_COMBINED = "non_context_aware_combined_summary"     # 先拼接全部页面再一次性摘要
    CONTEXT_AWARE = "context_aware_summary"
    CONTEXT_AWARE_CITATIONS = "context_aware_with_citations"
    WINDOWED_CONTEXT = "windowed_context"


@dataclass
class CompressedContent:
    """表示压缩后的内容"""
    original_length: int
    compressed_length: int
    content: str
    citations: List[Dict[str, str]] = field(default_factory=list)
    strategy: CompressionStrategy = CompressionStrategy.NO_COMPRESSION
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ContextCompressor:
    """负责执行各种上下文压缩策略"""
    
    def __init__(self, strategy: CompressionStrategy, api_key: str, enable_streaming: bool = True):
        """
        初始化上下文压缩器

        参数:
            strategy: 要使用的压缩策略
            api_key: LLM 的 API Key
            enable_streaming: 摘要时是否启用流式输出
        """
        self.strategy = strategy
        self.enable_streaming = enable_streaming
        # Moonshot 官方 key 存在则直连；否则回退 OpenRouter（见 Config.resolve_llm）。
        resolved_key, resolved_base_url, resolved_model = Config.resolve_llm()
        self.client = OpenAI(
            api_key=resolved_key,
            base_url=resolved_base_url
        )
        self.model = resolved_model
        
        # 初始化用于 token 计数的分词器
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4")
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        logger.info(f"Context compressor initialized with strategy: {strategy.value}, streaming: {enable_streaming}")
    
    def count_tokens(self, text: str) -> int:
        """统计一段文本的 token 数。"""
        try:
            return len(self.encoding.encode(text))
        except Exception:
            # 回退到按字符估算（1 token ≈ 4 字符）
            return len(text) // 4
    
    def compress_search_results(
        self, 
        search_results: Dict[str, Any],
        query: str,
        current_context: Optional[str] = None
    ) -> CompressedContent:
        """
        按所选策略压缩搜索结果

        参数:
            search_results: 网络工具返回的原始搜索结果
            query: 原始搜索查询
            current_context: 当前对话上下文（供上下文感知策略使用）

        返回:
            压缩后的内容
        """
        if self.strategy == CompressionStrategy.NO_COMPRESSION:
            return self._no_compression(search_results)
        elif self.strategy == CompressionStrategy.NON_CONTEXT_AWARE_INDIVIDUAL:
            return self._non_context_aware_individual_summary(search_results)
        elif self.strategy == CompressionStrategy.NON_CONTEXT_AWARE_COMBINED:
            return self._non_context_aware_combined_summary(search_results)
        elif self.strategy == CompressionStrategy.CONTEXT_AWARE:
            return self._context_aware_summary(search_results, query, current_context)
        elif self.strategy == CompressionStrategy.CONTEXT_AWARE_CITATIONS:
            return self._context_aware_with_citations(search_results, query, current_context)
        elif self.strategy == CompressionStrategy.WINDOWED_CONTEXT:
            # 窗口化策略返回完整内容（压缩延后进行）
            return self._no_compression(search_results)
        else:
            raise ValueError(f"Unknown compression strategy: {self.strategy}")
    
    def compress_for_history(
        self,
        content: str,
        tool_name: str,
        query: str,
        preserve_citations: bool = True
    ) -> CompressedContent:
        """
        压缩用于写入消息历史的内容（窗口化策略使用）

        参数:
            content: 待压缩内容
            tool_name: 生成该内容的工具名
            query: 触发这次工具调用的查询
            preserve_citations: 是否保留引用

        返回:
            用于历史的压缩内容
        """
        original_length = len(content)
        
        try:
            prompt = f"""Compress the following {tool_name} results into a concise summary that preserves key information.
Focus on information relevant to: {query}

Original content:
{content[:10000]}

Requirements:
1. Keep all important facts, names, dates, and affiliations
2. Remove redundant information
3. Maintain clarity and coherence
{"4. Include [Source: URL] citations for important facts" if preserve_citations else ""}
5. Maximum length: {Config.SUMMARY_MAX_TOKENS} tokens

Provide a focused summary:"""

            # 记录 prompt 长度
            prompt_tokens = self.count_tokens(prompt)
            logger.info(f"Simple summary request - Prompt tokens: {prompt_tokens}, Prompt length: {len(prompt)} chars")

            if self.enable_streaming:
                # 把摘要流式打印到控制台
                print(f"\n📝 Creating simple summary...\n", flush=True)
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that creates concise summaries."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=_reasoning_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS),
                    stream=True
                )
                
                summary_parts = []
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        # 注意：不要把这个变量命名为 `content` —— 那会遮蔽
                        # `content` 参数（原始工具输出），导致流中途失败时
                        # 下面的截断兜底逻辑失效。
                        delta_text = chunk.choices[0].delta.content
                        print(delta_text, end="", flush=True)
                        summary_parts.append(delta_text)
                print("\n")  # 流式输出结束后补换行
                compressed = "".join(summary_parts)
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that creates concise summaries."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=_reasoning_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS)
                )
                compressed = response.choices[0].message.content
            
            return CompressedContent(
                original_length=original_length,
                compressed_length=len(compressed),
                content=compressed,
                strategy=CompressionStrategy.WINDOWED_CONTEXT
            )
            
        except Exception as e:
            logger.error(f"Error compressing for history: {str(e)}")
            # 回退到截断
            truncated = content[:2000] + "\n\n[Content truncated for history...]"
            return CompressedContent(
                original_length=original_length,
                compressed_length=len(truncated),
                content=truncated,
                strategy=CompressionStrategy.WINDOWED_CONTEXT
            )
    
    def _no_compression(self, search_results: Dict[str, Any]) -> CompressedContent:
        """
        策略 1：不压缩 —— 返回全部原始内容
        """
        all_content = []
        total_length = 0
        
        for result in search_results.get('results', []):
            content = f"""
===== Search Result =====
Title: {result.get('title', 'N/A')}
URL: {result.get('url', 'N/A')}
Snippet: {result.get('snippet', 'N/A')}

Full Content:
{result.get('content', 'No content available')}
========================
"""
            all_content.append(content)
            total_length += len(result.get('content') or '')
        
        full_content = "\n\n".join(all_content)
        
        return CompressedContent(
            original_length=total_length,
            compressed_length=len(full_content),
            content=full_content,
            strategy=CompressionStrategy.NO_COMPRESSION
        )
    
    def _non_context_aware_individual_summary(self, search_results: Dict[str, Any]) -> CompressedContent:
        """
        策略 2A：非上下文感知摘要 —— 逐页分别摘要后拼接
        """
        summaries = []
        total_original = 0
        
        for result in search_results.get('results', []):
            if not result.get('content'):
                continue
                
            original_content = result.get('content', '')
            total_original += len(original_content)
            
            try:
                # 独立摘要每一页
                prompt = f"""Summarize the following webpage content in 2-3 paragraphs:

Title: {result.get('title', 'N/A')}
URL: {result.get('url', 'N/A')}

Content:
{original_content[:5000]}

Provide a concise summary:"""

                # 记录 prompt 长度
                prompt_tokens = self.count_tokens(prompt)
                logger.info(f"Non-context-aware summary - Prompt tokens: {prompt_tokens}, Prompt length: {len(prompt)} chars")

                if self.enable_streaming:
                    # 把摘要流式打印到控制台
                    print(f"\n📝 Summarizing: {result.get('title', 'N/A')[:50]}...", end=" ", flush=True)
                    stream = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that creates concise summaries."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=_reasoning_safe_temperature(self.model, 0.3),
                        max_tokens=_reasoning_safe_max_tokens(self.model, 300),
                        stream=True
                    )
                    
                    summary_parts = []
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            print(content, end="", flush=True)
                            summary_parts.append(content)
                    print()  # 流式输出结束后换行
                    summary = "".join(summary_parts)
                else:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that creates concise summaries."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=_reasoning_safe_temperature(self.model, 0.3),
                        max_tokens=_reasoning_safe_max_tokens(self.model, 300)
                    )
                    summary = response.choices[0].message.content
                
                summaries.append(f"""
Source: {result.get('title', 'N/A')}
URL: {result.get('url', 'N/A')}
Summary: {summary}
""")
                
            except Exception as e:
                logger.error(f"Error summarizing page: {str(e)}")
                # 回退到搜索结果自带的 snippet
                summaries.append(f"""
Source: {result.get('title', 'N/A')}
URL: {result.get('url', 'N/A')}
Summary: {result.get('snippet', 'No summary available')}
""")
        
        compressed_content = "\n".join(summaries)
        
        return CompressedContent(
            original_length=total_original,
            compressed_length=len(compressed_content),
            content=compressed_content,
            strategy=CompressionStrategy.NON_CONTEXT_AWARE_INDIVIDUAL
        )
    
    def _non_context_aware_combined_summary(self, search_results: Dict[str, Any]) -> CompressedContent:
        """
        策略 2B：非上下文感知摘要 —— 拼接全部页面后一次性摘要
        """
        # 先合并全部内容
        all_content = []
        total_original = 0
        max_chars_per_page = 5000  # 限制每页长度，避免 token 溢出
        
        for result in search_results.get('results', []):
            if result.get('content'):
                original_content = result.get('content', '')
                total_original += len(original_content)
                
                # 限制每页内容的长度
                limited_content = original_content[:max_chars_per_page]
                
                all_content.append(f"""
===== Page: {result.get('title', 'N/A')} =====
URL: {result.get('url', 'N/A')}
Content: {limited_content}
""")
        
        if not all_content:
            return CompressedContent(
                original_length=0,
                compressed_length=0,
                content="No content available",
                strategy=CompressionStrategy.NON_CONTEXT_AWARE_COMBINED
            )
        
        combined_content = "\n\n".join(all_content)
        
        try:
            # 为合并后的全部内容生成一份摘要
            prompt = f"""Summarize the following combined webpage content comprehensively:

{combined_content}

Requirements:
1. Create a comprehensive summary covering all pages
2. Include key information from each source
3. Maintain factual accuracy
4. Maximum length: {Config.SUMMARY_MAX_TOKENS} tokens

Provide a comprehensive summary:"""

            # 记录 prompt 长度
            prompt_tokens = self.count_tokens(prompt)
            logger.info(f"Non-context-aware combined summary - Prompt tokens: {prompt_tokens}, Prompt length: {len(prompt)} chars")

            if self.enable_streaming:
                # 把摘要流式打印到控制台
                print(f"\n📄 Creating combined summary for all {len(search_results.get('results', []))} pages...\n", flush=True)
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that creates comprehensive summaries."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=_reasoning_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS),
                    stream=True
                )
                
                summary_parts = []
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        summary_parts.append(content)
                print("\n")  # 流式输出结束后补换行
                summary = "".join(summary_parts)
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that creates comprehensive summaries."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=_reasoning_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS)
                )
                summary = response.choices[0].message.content
            
            return CompressedContent(
                original_length=total_original,
                compressed_length=len(summary),
                content=summary,
                strategy=CompressionStrategy.NON_CONTEXT_AWARE_COMBINED
            )
            
        except Exception as e:
            logger.error(f"Error creating combined summary: {str(e)}")
            # 回退到拼接的 snippet
            fallback = "\n\n".join([
                f"{r.get('title', 'N/A')}: {r.get('snippet', 'No summary available')}"
                for r in search_results.get('results', [])
            ])
            return CompressedContent(
                original_length=total_original,
                compressed_length=len(fallback),
                content=fallback,
                strategy=CompressionStrategy.NON_CONTEXT_AWARE_COMBINED
            )
    
    def _context_aware_summary(
        self, 
        search_results: Dict[str, Any],
        query: str,
        current_context: Optional[str] = None
    ) -> CompressedContent:
        """
        策略 3：结合查询的上下文感知摘要
        """
        # 合并全部内容，并按页限长
        all_content = []
        total_original = 0
        max_chars_per_page = 5000  # 限制每页长度，避免 token 溢出
        
        for result in search_results.get('results', []):
            if result.get('content'):
                original_content = result.get('content', '')
                total_original += len(original_content)
                
                # 限制每页内容的长度
                limited_content = original_content[:max_chars_per_page]
                
                all_content.append(f"""
Title: {result.get('title', 'N/A')}
URL: {result.get('url', 'N/A')}
Content: {limited_content}
""")
        
        combined_content = "\n\n".join(all_content)
        
        try:
            # 生成上下文感知摘要
            prompt = f"""Given the search query: "{query}"
{f"Current context: {current_context[:1000]}" if current_context else ""}

Analyze the following search results and provide a focused summary that directly addresses the query.
Focus on extracting information most relevant to answering: {query}

Search Results:
{combined_content}

Requirements:
1. Focus only on information relevant to the query
2. Prioritize current/recent information
3. Include specific names, dates, and affiliations
4. Maximum length: {Config.SUMMARY_MAX_TOKENS} tokens

Provide a query-focused summary:"""

            # 记录 prompt 长度
            prompt_tokens = self.count_tokens(prompt)
            logger.info(f"Context-aware summary - Prompt tokens: {prompt_tokens}, Prompt length: {len(prompt)} chars")

            if self.enable_streaming:
                # 把摘要流式打印到控制台
                print(f"\n🎯 Creating context-aware summary for query: '{query[:50]}...'\n", flush=True)
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that creates focused, context-aware summaries."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=_reasoning_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS),
                    stream=True
                )
                
                summary_parts = []
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        summary_parts.append(content)
                print("\n")  # 流式输出结束后补换行
                summary = "".join(summary_parts)
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that creates focused, context-aware summaries."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=_reasoning_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS)
                )
                summary = response.choices[0].message.content
            
            return CompressedContent(
                original_length=total_original,
                compressed_length=len(summary),
                content=summary,
                strategy=CompressionStrategy.CONTEXT_AWARE
            )
            
        except Exception as e:
            logger.error(f"Error creating context-aware summary: {str(e)}")
            # 回退到简单拼接
            fallback = "\n\n".join([r.get('snippet', '') for r in search_results.get('results', [])])
            return CompressedContent(
                original_length=total_original,
                compressed_length=len(fallback),
                content=fallback,
                strategy=CompressionStrategy.CONTEXT_AWARE
            )
    
    def _context_aware_with_citations(
        self,
        search_results: Dict[str, Any],
        query: str,
        current_context: Optional[str] = None
    ) -> CompressedContent:
        """
        策略 4：带引用的上下文感知摘要
        """
        # 记录来源信息，并按页限长
        sources = []
        all_content = []
        total_original = 0
        max_chars_per_page = 5000  # 限制每页长度，避免 token 溢出
        
        for i, result in enumerate(search_results.get('results', [])):
            if result.get('content'):
                source_id = f"[{i+1}]"
                original_content = result.get('content', '')
                total_original += len(original_content)
                
                # 限制每页内容的长度
                limited_content = original_content[:max_chars_per_page]
                
                sources.append({
                    'id': source_id,
                    'title': result.get('title', 'N/A'),
                    'url': result.get('url', 'N/A')
                })
                
                all_content.append(f"""
{source_id} Title: {result.get('title', 'N/A')}
Content: {limited_content}
""")
        
        combined_content = "\n\n".join(all_content)
        
        try:
            # 生成带引用的上下文感知摘要
            prompt = f"""Given the search query: "{query}"
{f"Current context: {current_context[:1000]}" if current_context else ""}

Analyze the following search results and provide a focused summary with citations.

Search Results (with source IDs):
{combined_content}

Requirements:
1. Focus on information relevant to: {query}
2. Include inline citations using [1], [2], etc. for each fact
3. Prioritize current/recent information
4. Include specific names, dates, and affiliations with citations
5. Maximum length: {Config.SUMMARY_MAX_TOKENS} tokens

Provide a query-focused summary with citations:"""

            # 记录 prompt 长度
            prompt_tokens = self.count_tokens(prompt)
            logger.info(f"Citation-based summary - Prompt tokens: {prompt_tokens}, Prompt length: {len(prompt)} chars")

            if self.enable_streaming:
                # 把摘要流式打印到控制台
                print(f"\n📚 Creating summary with citations for: '{query[:50]}...'\n", flush=True)
                stream = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that creates focused summaries with proper citations."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=_reasoning_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS),
                    stream=True
                )
                
                summary_parts = []
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        print(content, end="", flush=True)
                        summary_parts.append(content)
                print("\n")  # 流式输出结束后补换行
                summary = "".join(summary_parts)
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that creates focused summaries with proper citations."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=_reasoning_safe_temperature(self.model, 0.3),
                    max_tokens=_reasoning_safe_max_tokens(self.model, Config.SUMMARY_MAX_TOKENS)
                )
                summary = response.choices[0].message.content
            
            # 追加来源列表
            source_list = "\n\nSources:\n"
            for source in sources:
                source_list += f"{source['id']} {source['title']} - {source['url']}\n"
            
            final_content = summary + source_list
            
            return CompressedContent(
                original_length=total_original,
                compressed_length=len(final_content),
                content=final_content,
                citations=sources,
                strategy=CompressionStrategy.CONTEXT_AWARE_CITATIONS
            )
            
        except Exception as e:
            logger.error(f"Error creating summary with citations: {str(e)}")
            # 兜底
            fallback = "\n\n".join([
                f"[{i+1}] {r.get('title', '')}: {r.get('snippet', '')}"
                for i, r in enumerate(search_results.get('results', []))
            ])
            return CompressedContent(
                original_length=total_original,
                compressed_length=len(fallback),
                content=fallback,
                citations=sources,
                strategy=CompressionStrategy.CONTEXT_AWARE_CITATIONS
            )
    
    def estimate_tokens(self, text: str) -> int:
        """
        估算文本的 token 数（粗略近似）

        参数:
            text: 待估算的文本

        返回:
            估算的 token 数
        """
        # 粗略近似：1 token ≈ 4 字符
        return len(text) // 4
