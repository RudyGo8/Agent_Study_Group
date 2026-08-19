"""
带注意力可视化的 ReAct 工具调用 Agent
实现规范的 ReAct（Reasoning + Acting）循环，并可逐步可视化
"""

import json
import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from agent import AttentionVisualizationAgent, GenerationResult
from tools import ToolRegistry
import time

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ReActStep:
    """表示 ReAct 推理过程中的一步"""
    step_number: int
    step_type: str  # 'thought', 'action', 'observation', 'answer'
    content: str
    tool_call: Optional[Dict[str, Any]] = None
    tool_result: Optional[str] = None
    
    def to_dict(self):
        return {
            'step_number': self.step_number,
            'step_type': self.step_type,
            'content': self.content,
            'tool_call': self.tool_call,
            'tool_result': self.tool_result
        }


class ReActAttentionAgent(AttentionVisualizationAgent):
    """
    实现规范 Thought-Action-Observation 循环的 ReAct Agent，
    并在每一步追踪注意力
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tool_registry = ToolRegistry()
        self.max_iterations = 10  # 为复杂推理留足迭代次数
        self.trajectory_data = []  # 保存本次会话的轨迹数据

    def create_initial_messages(self, query: str) -> list:
        """按 Qwen3 要求的格式创建初始消息"""
        system_prompt = """You are a helpful AI assistant. Always use tools when you need specific information or calculations."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query}
        ]
        
        return messages
    
    def parse_tool_calls(self, text: str) -> List[Dict[str, Any]]:
        """按 Qwen3 格式从 Agent 响应中解析工具调用"""
        tool_calls = []

        # 查找 <tool_call> 标签（Qwen3 格式）
        tool_pattern = r'<tool_call>(.*?)</tool_call>'
        tool_matches = re.findall(tool_pattern, text, re.DOTALL)
        
        for match in tool_matches:
            try:
                # 解析 tool_call 标签内的 JSON
                tool_data = json.loads(match.strip())
                if "name" in tool_data and "arguments" in tool_data:
                    tool_calls.append(tool_data)
                    logger.info(f"Parsed tool call: {tool_data['name']}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse tool call: {e}")
                logger.debug(f"Content was: {match}")
        
        return tool_calls
    
    def generate_with_streaming(
        self,
        prompt: str,
        max_new_tokens: int = 2000,
        temperature: float = 0.3,
        verbose: bool = True,
        show_token_ids: bool = False,
        track_attention: bool = True
    ) -> tuple:
        """
        逐 token 流式生成文本，遇到 EOS 停止

        Args:
            prompt: 输入提示
            max_new_tokens: 最多生成的 token 数
            temperature: 采样温度
            verbose: 是否将 token 流式打印到控制台
            show_token_ids: 是否在文本旁显示 token ID
            track_attention: 是否追踪注意力权重

        Returns:
            (generated_text, attention_weights) 元组
        """
        import torch

        # 对输入分词时不截断，保留全部 token
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=False)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        input_length = inputs['input_ids'].shape[1]
        
        # 获取 EOS token ID
        eos_token_id = self.tokenizer.eos_token_id
        if isinstance(eos_token_id, list):
            eos_token_ids = eos_token_id
        else:
            eos_token_ids = [eos_token_id] if eos_token_id else []
        
        # 添加常见停止 token
        stop_tokens = set(eos_token_ids)
        if hasattr(self.tokenizer, 'pad_token_id') and self.tokenizer.pad_token_id:
            stop_tokens.add(self.tokenizer.pad_token_id)
        
        # 添加可能标志生成结束的特殊 token
        special_stop_strings = ['<|endoftext|>', '<|im_end|>', '</s>', '[DONE]']
        
        generated_ids = []
        generated_text = ""
        attention_weights = [] if track_attention else None
        
        if verbose:
            print(f"📊 Input: {input_length} tokens | Max new: {max_new_tokens}")
            print("🔤 Streaming output:", flush=True)
            print("-" * 60, flush=True)
        
        # 逐 token 生成
        with torch.no_grad():
            past_key_values = None
            input_ids = inputs['input_ids']
            
            for i in range(max_new_tokens):
                # 前向传播并输出注意力
                outputs = self.model(
                    input_ids=input_ids,
                    past_key_values=past_key_values,
                    use_cache=True,
                    return_dict=True,
                    output_attentions=track_attention
                )
                
                # 获取下一个 token 的 logits
                logits = outputs.logits[0, -1, :] / temperature
                
                # 采样下一个 token
                probs = torch.nn.functional.softmax(logits, dim=-1)
                next_token_id = torch.multinomial(probs, num_samples=1).item()
                
                # 如有要求则追踪注意力
                if track_attention and hasattr(outputs, 'attentions') and outputs.attentions:
                    # 取最后一层注意力，各头取最大值
                    last_attn = outputs.attentions[-1]  # [batch, heads, seq, seq]
                    max_attn = last_attn[0, :, -1, :].max(dim=0)[0].cpu().numpy()  # 对各头取最大值
                    attention_weights.append(max_attn)
                
                # 检查 EOS
                if next_token_id in stop_tokens:
                    if verbose:
                        print(f"\n🛑 [EOS token detected: {next_token_id}]", flush=True)
                        print(f"📈 Generated {len(generated_ids)} tokens total")
                    break
                
                # 解码并流式输出 token
                token_text = self.tokenizer.decode([next_token_id], skip_special_tokens=False)
                generated_ids.append(next_token_id)
                generated_text += token_text
                
                if verbose:
                    # 将 token 流式打印到控制台（显示时跳过特殊 token）
                    display_text = self.tokenizer.decode([next_token_id], skip_special_tokens=True)
                    if display_text:  # 只在有可见文本时打印
                        if show_token_ids:
                            print(f"[{next_token_id}:{display_text}]", end="", flush=True)
                        else:
                            print(display_text, end="", flush=True)
                
                # 在已累积文本中检查停止字符串
                for stop_str in special_stop_strings:
                    if stop_str in generated_text:
                        if verbose:
                            print(f"\n🛑 [Stop string detected: {stop_str}]", flush=True)
                            print(f"📈 Generated {len(generated_ids)} tokens")
                        return generated_text[:generated_text.index(stop_str)], attention_weights
                
                # 更新下一次迭代的输入
                input_ids = torch.tensor([[next_token_id]], device=self.device)
                past_key_values = outputs.past_key_values
        
        if verbose:
            print(f"\n{'-' * 60}")
            print(f"📈 Total generated: {len(generated_ids)} tokens")
        
        return generated_text, attention_weights
    
    def generate_with_attention_streaming(
        self,
        prompt: str,
        max_new_tokens: int = 2000,
        temperature: float = 0.3,
        verbose: bool = True,
        save_trajectory: bool = False
    ) -> GenerationResult:
        """
        流式生成文本并追踪注意力，返回 GenerationResult 格式

        Args:
            prompt: 输入提示
            max_new_tokens: 最多生成的 token 数
            temperature: 采样温度
            verbose: 是否将 token 流式打印到控制台
            save_trajectory: 是否保存轨迹（未使用，保留是为了兼容）

        Returns:
            含 token 和注意力信息的 GenerationResult 对象
        """
        from agent import AttentionStep
        import torch

        # 使用流式生成方法（流式期间不追踪注意力）
        generated_text, _ = self.generate_with_streaming(
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            verbose=verbose,
            track_attention=False  # 流式期间不追踪
        )

        # 分词以获得输入和输出 token
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=False)
        input_token_ids = inputs['input_ids'][0].tolist()
        input_tokens = [self.tokenizer.decode([tid], skip_special_tokens=False) for tid in input_token_ids]
        
        # 获取输出 token 及其 ID
        output_token_ids = self.tokenizer(generated_text, return_tensors="pt", truncation=False)['input_ids'][0].tolist()
        output_tokens = [self.tokenizer.decode([tid], skip_special_tokens=False) for tid in output_token_ids]
        
        # 再做一次前向传播，获取完整序列的完整注意力矩阵
        full_text = prompt + generated_text
        full_inputs = self.tokenizer(full_text, return_tensors="pt", truncation=False)
        full_inputs = {k: v.to(self.device) for k, v in full_inputs.items()}
        
        # 一次前向传播拿到完整注意力矩阵
        attention_matrix = []
        with torch.no_grad():
            outputs = self.model(
                **full_inputs,
                output_attentions=True,
                return_dict=True
            )
            
            if hasattr(outputs, 'attentions') and outputs.attentions:
                # 取最后一层的注意力
                last_layer_attn = outputs.attentions[-1]  # [batch, heads, seq, seq]
                # 各头取平均并取出 batch 0
                avg_attn = last_layer_attn[0].mean(dim=0).cpu().numpy()  # [seq, seq]

                # 只提取输出 token 所在行（来自输出 token 的注意力）
                # 需要每个输出 token 对此前所有 token 的注意力
                output_start_idx = len(input_tokens)
                for i in range(len(output_tokens)):
                    token_idx = output_start_idx + i
                    if token_idx < avg_attn.shape[0]:
                        # 取该输出 token 对此前所有 token（含输入）的注意力
                        attn_row = avg_attn[token_idx, :token_idx+1].tolist()
                        attention_matrix.append(attn_row)
        
        # 构建注意力步骤
        attention_steps = []
        for i, attn_row in enumerate(attention_matrix):
            if i < len(output_tokens) and i < len(output_token_ids):
                step = AttentionStep(
                    step=i,
                    token_id=output_token_ids[i],
                    token=output_tokens[i],
                    position=len(input_tokens) + i,
                    attention_weights=[attn_row]  # 包装成二维数组以匹配 AttentionStep 数据类
                )
                attention_steps.append(step)
        
        # 构建并返回 GenerationResult
        all_tokens = input_tokens + output_tokens
        
        return GenerationResult(
            input_text=prompt,
            output_text=generated_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens=all_tokens,
            attention_steps=attention_steps,
            context_length=len(input_tokens)
        )
    
    def execute_react_loop(
        self,
        query: str,
        temperature: float = 0.3,
        max_new_tokens: int = 2000,
        verbose: bool = True,
        save_attention: bool = True
    ) -> List[ReActStep]:
        """
        针对给定查询执行 ReAct 循环

        Args:
            query: 要回答的用户查询
            temperature: 采样温度
            max_new_tokens: 每次响应最多生成的 token 数
            verbose: 是否打印进度
            save_attention: 是否保存注意力可视化

        Returns:
            表示推理过程的 ReActStep 对象列表
        """
        from pathlib import Path
        import numpy as np
        import matplotlib.pyplot as plt
        
        steps = []
        step_counter = 0
        final_answer = None
        
        # 创建注意力图的输出目录
        if save_attention:
            output_dir = Path("agent_demo_results")
            output_dir.mkdir(exist_ok=True)
            attention_dir = output_dir / "attention_maps"
            attention_dir.mkdir(exist_ok=True)
        
        # 初始化消息
        messages = self.create_initial_messages(query)
        tools = self.tool_registry.get_tool_schemas()
        
        if verbose:
            print("=" * 60)
            print("Starting ReAct Reasoning Loop")
            print("=" * 60)
            print(f"\n📝 Query: {query}\n")
        
        for iteration in range(self.max_iterations):
            step_counter += 1
            
            if verbose:
                print(f"\n--- Step {step_counter} ---")
            
            # 应用带工具的聊天模板
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tools=tools,
                tokenize=False,
                add_generation_prompt=True
            )
            
            # 流式生成响应并追踪注意力
            # 边生成边显示 token，同时收集注意力数据
            result = self.generate_with_attention_streaming(
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                verbose=verbose,  # 启用流式输出
                save_trajectory=False  # 不单独保存轨迹
            )
            
            response_text = result.output_text
            attention_weights = []
            
            # 从结果中提取注意力权重
            if result.attention_steps:
                for step in result.attention_steps:
                    if step.attention_weights:
                        # step.attention_weights 是 [[row]]，这里只要 [row]
                        attention_weights.append(step.attention_weights[0] if step.attention_weights else [])
            
            if verbose and attention_weights:
                print(f"\n📊 Generated {len(result.output_tokens)} tokens with {len(attention_weights)} attention steps")
            
            # 保存本次 LLM 调用的完整注意力数据
            if save_attention:
                self.trajectory_data.append({
                    "step_num": step_counter,
                    "prompt": prompt,
                    "response": response_text,
                    "input_tokens": result.input_tokens,  # 完整输入 token
                    "output_tokens": result.output_tokens,  # 仅输出 token
                    "all_tokens": result.tokens if hasattr(result, 'tokens') else (result.input_tokens + result.output_tokens),  # 完整序列
                    "attention_matrix": attention_weights,
                    "attention_steps": [step.to_dict() for step in result.attention_steps] if result.attention_steps else [],
                    "step_type": 'reasoning' if '<think>' in response_text else 'action',
                    "tool_info": {'tools_used': [tc['name'] for tc in self.parse_tool_calls(response_text)]},
                    "token_count": len(result.input_tokens) + len(result.output_tokens)
                })
            
            # 将助手响应加入消息
            messages.append({"role": "assistant", "content": response_text})
            
            # 若存在则从 <think> 标签提取思考内容
            think_match = re.search(r'<think>(.*?)</think>', response_text, re.DOTALL)
            if think_match:
                thought = think_match.group(1).strip()
                if thought and verbose:
                    print(f"\n🤔 Thinking: {thought}")
                if thought:
                    steps.append(ReActStep(
                        step_number=step_counter,
                        step_type='thought',
                        content=thought
                    ))
            
            # 解析工具调用
            tool_calls = self.parse_tool_calls(response_text)
            
            if tool_calls:
                # 处理每个工具调用
                for tool_call in tool_calls:
                    tool_name = tool_call['name']
                    tool_args = tool_call['arguments']
                    
                    if verbose:
                        print(f"\n🔧 Action: Calling {tool_name}")
                        print(f"   Args: {tool_args}")
                    
                    # 执行工具
                    tool_result = self.tool_registry.execute_tool(tool_name, tool_args)
                    
                    if verbose:
                        print(f"   Result: {tool_result}")
                    
                    # 记录 action 步骤
                    steps.append(ReActStep(
                        step_number=step_counter,
                        step_type='action',
                        content=f"Using tool: {tool_name}",
                        tool_call=tool_call,
                        tool_result=tool_result
                    ))
                    
                    # 以 user 消息加入工具响应（Qwen3 格式）
                    tool_response_msg = f"<tool_response>\n{tool_result}\n</tool_response>"
                    messages.append({"role": "user", "content": tool_response_msg})
                    
                    # 记录 observation
                    steps.append(ReActStep(
                        step_number=step_counter,
                        step_type='observation',
                        content=tool_result
                    ))
            else:
                # 未检测到工具调用——这就是停止条件
                if verbose:
                    print("\n📍 No tool calls in response. Stopping ReAct loop.")
                
                # 若存在则提取最终答案
                # 去掉 <think> 标签以获得干净内容
                clean_content = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()
                
                if clean_content:
                    final_answer = clean_content
                    if verbose:
                        print(f"\n✅ Final Answer: {final_answer[:200]}...")
                    
                    steps.append(ReActStep(
                        step_number=step_counter,
                        step_type='answer',
                        content=final_answer
                    ))
                
                # 未调用工具，停止循环
                break
        
        return steps
    
    def save_react_trajectory(self, query: str, steps: List[ReActStep], final_answer: str,
                              temperature: float = 0.3, max_tokens: int = 2000):
        """
        保存包含全部步骤的 ReAct 轨迹

        Args:
            query: 初始查询
            steps: ReAct 步骤列表
            final_answer: 生成的最终答案
            temperature: 生成所用温度
            max_tokens: 生成所用最大 token 数
        """
        from pathlib import Path
        import time
        import json
        
        # 创建输出目录
        output_dir = Path("frontend/public/trajectories")
        output_dir.mkdir(parents=True, exist_ok=True)

        # 用时间戳生成唯一文件名
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = output_dir / f"trajectory_{timestamp}.json"
        
        # 用 trajectory_data 中的注意力数据整理 LLM 调用
        llm_calls = []
        for traj_data in self.trajectory_data:
            # 正确提取注意力矩阵（仅输出 token）
            attention_matrix = []
            if traj_data.get('attention_matrix'):
                # 将注意力权重转为规范格式
                for weights in traj_data['attention_matrix']:
                    if isinstance(weights, list):
                        attention_matrix.append(weights)
                    elif hasattr(weights, 'tolist'):
                        attention_matrix.append(weights.tolist())
            
            # 有完整 token 序列就用，否则合并得到
            all_tokens = traj_data.get('all_tokens', [])
            if not all_tokens:
                # 兜底：不截断地合并输入和输出 token
                all_tokens = traj_data.get('input_tokens', []) + traj_data.get('output_tokens', [])
            
            # 完整保存提示与响应，不做任何截断
            llm_call = {
                "step_num": traj_data.get('step_num'),
                "step_type": traj_data.get('step_type', 'unknown'),
                "prompt": traj_data.get('prompt', ''),  # 完整提示文本，不截断
                "response": traj_data.get('response', ''),  # 完整响应文本
                "tokens": all_tokens,  # 完整 token 序列
                "input_tokens": traj_data.get('input_tokens', []),  # 完整输入 token
                "output_tokens": traj_data.get('output_tokens', []),  # 完整输出 token
                "input_token_count": len(traj_data.get('input_tokens', [])),
                "output_token_count": len(traj_data.get('output_tokens', [])),
                "total_token_count": traj_data.get('token_count', len(all_tokens)),
                "attention_data": {
                    "tokens": all_tokens,
                    "attention_matrix": attention_matrix,
                    "num_layers": 1,
                    "num_heads": len(attention_matrix[0]) if attention_matrix and attention_matrix[0] else 0,
                    "output_only": True,  # 仅输出 token 的注意力
                    "context_length": traj_data.get('input_token_count', len(traj_data.get('input_tokens', [])))
                },
                "tool_info": traj_data.get('tool_info', {})
            }
            llm_calls.append(llm_call)
        
        # 汇总所有步骤内容作为摘要
        combined_response = []
        for step in steps:
            combined_response.append(f"[{step.step_type.upper()}] {step.content}")
            if step.tool_result:
                combined_response.append(f"[OBSERVATION] {step.tool_result}")
        
        # 准备包含多次 LLM 调用的轨迹数据
        trajectory_data = {
            "id": timestamp,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "test_case": {
                "category": "ReAct",
                "query": query,
                "description": f"ReAct agent trajectory with {len(llm_calls)} LLM calls and {len(steps)} reasoning steps"
            },
            "response": final_answer if final_answer else "\\n\\n".join(combined_response),
            "llm_calls": llm_calls,  # 多次 LLM 调用，各带独立注意力图
            "reasoning_steps": [step.to_dict() for step in steps],  # ReAct 步骤备查
            "tokens": llm_calls[0]["tokens"] if llm_calls else [],  # 兼容字段
            "attention_data": {  # 主展示用第一次 LLM 调用的注意力
                "tokens": llm_calls[0]["tokens"] if llm_calls else [],
                "attention_matrix": llm_calls[0]["attention_data"]["attention_matrix"] if llm_calls else [],
                "num_layers": 1,
                "num_heads": llm_calls[0]["attention_data"]["num_heads"] if llm_calls else 0,
                "output_only": True,  # 仅输出 token 的注意力
                "context_length": llm_calls[0]["attention_data"].get("context_length", 0) if llm_calls else 0
            },
            "metadata": {
                "model": self.model_name,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "device": str(self.device),
                "total_llm_calls": len(llm_calls),
                "total_steps": len(steps),
                "attention_type": "output_only",  # 注明注意力类型
                "step_breakdown": {
                    step_type: sum(1 for s in steps if s.step_type == step_type)
                    for step_type in set(s.step_type for s in steps)
                }
            }
        }
        
        # 保存到文件
        with open(filename, 'w') as f:
            json.dump(trajectory_data, f, indent=2, default=str)

        # 更新清单
        manifest_file = output_dir / "manifest.json"
        manifest = []
        if manifest_file.exists():
            try:
                with open(manifest_file, 'r') as f:
                    manifest = json.load(f)
            except Exception:
                manifest = []
        
        manifest.append({
            "filename": f"trajectory_{timestamp}.json",
            "id": timestamp,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": "ReAct",
            "query": query
        })
        
        # 只保留最近 50 条轨迹
        manifest = manifest[-50:]
        
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"ReAct trajectory saved to {filename}")
        return str(filename)


def demonstrate_react_agent():
    """用多个查询演示 ReAct Agent"""
    print("=" * 60)
    print("ReAct Tool-Calling Agent Demo with Attention Tracking")
    print("=" * 60)
    
    # 初始化 Agent（verbose 用于 Agent 内部过程，不用于生成）
    agent = ReActAttentionAgent(verbose=False)

    # 来自最初需求的测试查询
    test_queries = [
        "What's the weather like in Vancouver right now?",
        "Calculate the exact compound interest on $5,000 invested at 6% annual interest rate for 30 years, compounded monthly.",
    ]
    
    all_results = []
    saved_trajectories = []
    
    # 逐个运行查询
    for i, query in enumerate(test_queries, 1):
        print(f"\n{'='*60}")
        print(f"Sample {i}: {query}")
        print(f"{'='*60}")
        
        # 为新查询清空轨迹数据
        agent.trajectory_data = []
        
        # 定义生成参数
        temperature = 0.7
        max_new_tokens = 2000
        
        # 用 ReAct 循环执行
        steps = agent.execute_react_loop(
            query,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
            verbose=True
        )
        
        # 展示摘要
        print(f"\n📊 Summary:")
        print(f"  • Total steps: {len(steps)}")
        print(f"  • Step breakdown:")
        
        step_counts = {}
        for step in steps:
            step_counts[step.step_type] = step_counts.get(step.step_type, 0) + 1
        
        for step_type, count in step_counts.items():
            print(f"    - {step_type}: {count}")
        
        # 获取最终答案
        final_answer = next((s.content for s in steps if s.step_type == 'answer'), "No answer generated")
        print(f"\n💬 Final Answer: {final_answer[:200]}...")
        
        all_results.append({
            'query': query,
            'steps': [s.to_dict() for s in steps],
            'final_answer': final_answer
        })
        
        # 保存完整轨迹
        trajectory_file = agent.save_react_trajectory(query, steps, final_answer, temperature, max_new_tokens)
        if trajectory_file:
            saved_trajectories.append(trajectory_file)
        
        print("-" * 40)
    
    # 保存结果
    output_dir = Path("agent_demo_results")
    output_dir.mkdir(exist_ok=True)
    
    with open(output_dir / "react_results.json", 'w') as f:
        json.dump(all_results, f, indent=2)
    
    # 可视化改由前端完成
    print(f"\n✨ To visualize attention patterns:")
    print(f"   1. Run the frontend: cd frontend && npm run dev")
    print(f"   2. Open http://localhost:3000 in your browser")
    print(f"\n💾 {len(saved_trajectories)} trajectories saved to frontend/public/trajectories/")
    
    print(f"\n✅ Results saved to {output_dir}/")
    
    return all_results


if __name__ == "__main__":
    import sys
    
    print("\nThis demonstrates a proper ReAct agent that:")
    print("  • Uses structured reasoning (Thought -> Action -> Observation)")
    print("  • Calls tools when needed for information")
    print("  • Tracks attention at each reasoning step")
    print("  • Generates as many tokens as needed (no limits!)")
    print("\nThe agent now properly reasons about problems and uses tools!")
    print("=" * 60)

    # 运行演示
    demonstrate_react_agent()
        
    print("\n" + "=" * 60)
    print("✨ Demo complete!")