"""
注意力可视化 Agent
将 Qwen3 0.5B 模型与注意力追踪和可视化集成
"""

import json
import logging
import torch
import numpy as np
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    LogitsProcessorList,
    LogitsProcessor,
    GenerationConfig
)
import warnings
warnings.filterwarnings("ignore")

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AttentionStep:
    """记录单个生成步骤的注意力信息"""
    step: int
    token_id: int
    token: str
    position: int
    attention_weights: List[List[float]]  # [num_heads x seq_len] 或平均后的 [seq_len]
    
    def to_dict(self):
        """转换为字典以便 JSON 序列化"""
        return {
            'step': self.step,
            'token_id': self.token_id, 
            'token': self.token,
            'position': self.position,
            'attention_weights': self.attention_weights
        }


@dataclass  
class GenerationResult:
    """带注意力追踪的一次完整生成结果"""
    input_text: str
    output_text: str
    input_tokens: List[str]
    output_tokens: List[str]
    attention_steps: List[AttentionStep]
    context_length: int
    response: str = ""  # 兼容字段
    tokens: List[str] = field(default_factory=list)  # 兼容字段
    attention_weights: Dict = field(default_factory=dict)  # 兼容字段
    
    def __post_init__(self):
        if not self.tokens:
            self.tokens = self.input_tokens + self.output_tokens
        if not self.response:
            self.response = self.output_text
    
    def to_dict(self):
        """转换为字典以便 JSON 序列化"""
        return {
            'input_text': self.input_text,
            'output_text': self.output_text,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'attention_steps': [step.to_dict() for step in self.attention_steps],
            'context_length': self.context_length,
            'response': self.response,
            'tokens': self.tokens
        }


class AttentionTracker(LogitsProcessor):
    """
    在生成过程中追踪注意力权重的 LogitsProcessor
    """
    
    def __init__(self, tokenizer, context_length: int, verbose: bool = False):
        self.tokenizer = tokenizer
        self.context_length = context_length
        self.verbose = verbose
        self.attention_cache = {}
        self.generation_step = 0
        self.generated_tokens = []
        self.output_only = True  # 只追踪输出 token 的注意力
        
    def reset(self):
        """为新一轮生成重置追踪器"""
        self.attention_cache = {}
        self.generation_step = 0
        self.generated_tokens = []
        
    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        """生成过程中被调用，用于追踪 token"""
        self.generation_step += 1
        
        # 追踪已生成的 token
        if input_ids.shape[1] > self.context_length:
            last_token_id = input_ids[0, -1].item()
            last_token = self.tokenizer.decode([last_token_id])
            current_position = input_ids.shape[1] - 1
            
            self.generated_tokens.append({
                'step': self.generation_step,
                'token_id': last_token_id,
                'token': last_token,
                'position': current_position
            })
            
            if self.verbose:
                print(f"  Step {self.generation_step}: Generated '{last_token}' at position {current_position}")
                
        return scores
    
    def update_attention(self, position: int, attention_weights):
        """存储某个位置的注意力权重（仅针对输出 token）"""
        # 只存储输出 token 的注意力（位置 >= context_length）
        if self.output_only and position < self.context_length:
            return  # 跳过输入 token 的注意力
        self.attention_cache[position] = attention_weights
        
    def get_attention_steps(self) -> List[AttentionStep]:
        """将缓存数据转换为 AttentionStep 对象"""
        steps = []
        for token_info in self.generated_tokens:
            position = token_info['position']
            if position in self.attention_cache:
                attention = self.attention_cache[position]
                if isinstance(attention, torch.Tensor):
                    attention = attention.cpu().numpy().tolist()
                elif isinstance(attention, np.ndarray):
                    attention = attention.tolist()
                    
                steps.append(AttentionStep(
                    step=token_info['step'],
                    token_id=token_info['token_id'],
                    token=token_info['token'],
                    position=position,
                    attention_weights=attention
                ))
        return steps


class AttentionVisualizationAgent:
    """
    使用 Qwen3 0.6B 生成文本并追踪注意力权重的 Agent
    """
    
    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-0.6B",
        device: Optional[str] = None,
        attention_layer_index: int = -1,
        verbose: bool = True
    ):
        """
        用 Qwen3 模型初始化 Agent

        Args:
            model_name: Hugging Face 模型名
            device: 运行设备（cuda/mps/cpu）
            attention_layer_index: 追踪哪一层的注意力（-1 表示最后一层）
            verbose: 是否打印调试信息
        """
        self.model_name = model_name
        self.attention_layer_index = attention_layer_index
        self.verbose = verbose
        
        # 检测设备
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else \
                         "mps" if torch.backends.mps.is_available() else "cpu"
        else:
            self.device = device
            
        logger.info(f"Initializing {model_name} on {self.device}")
        
        # 加载模型和分词器
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
            
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float32 if self.device == "cpu" else torch.float16,
            trust_remote_code=True,
            attn_implementation="eager"  # 启用注意力输出
        ).to(self.device)
        
        # 确定层数
        self.num_layers = self._get_num_layers()
        if self.num_layers:
            logger.info(f"Model has {self.num_layers} layers")
            
        # 初始化注意力追踪器
        self.tracker = None
        self.conversation_history = []
        
    def _get_num_layers(self) -> Optional[int]:
        """获取模型中 transformer 层的数量"""
        if hasattr(self.model, 'config'):
            for attr in ['num_hidden_layers', 'n_layer', 'num_layers']:
                if hasattr(self.model.config, attr):
                    return getattr(self.model.config, attr)
        return None
    
    def _capture_attention_hook(self, module, input, output):
        """捕获模型层注意力权重的钩子"""
        if self.tracker is None:
            return
            
        try:
            attention_weights = None
            
            # 尝试多种方式提取注意力
            if hasattr(output, 'attentions') and output.attentions is not None:
                attention_weights = output.attentions
            elif isinstance(output, tuple) and len(output) > 1:
                for item in output:
                    if isinstance(item, torch.Tensor) and len(item.shape) == 4:
                        attention_weights = item
                        break
                        
            if attention_weights is not None:
                # 处理多层情况
                if isinstance(attention_weights, (list, tuple)):
                    layer_idx = self.attention_layer_index
                    if layer_idx >= 0 and layer_idx < len(attention_weights):
                        attention_weights = attention_weights[layer_idx]
                    else:
                        attention_weights = attention_weights[-1]  # 默认取最后一层
                        
                # 提取最后一个 token 的注意力
                if isinstance(attention_weights, torch.Tensor) and attention_weights.dim() >= 3:
                    if attention_weights.dim() == 4:
                        # 各头取平均：[batch, heads, seq, seq] -> [seq]
                        avg_attention = attention_weights[0, :, -1, :].mean(dim=0)
                    else:
                        avg_attention = attention_weights[0, -1, :]
                        
                    current_pos = avg_attention.shape[0] - 1
                    
                    # 只追踪输出 token 的注意力
                    if current_pos >= self.tracker.context_length:
                        self.tracker.update_attention(current_pos, avg_attention)
                    
        except Exception as e:
            if self.verbose:
                logger.warning(f"Error in attention hook: {e}")
    
    def save_trajectory(self, result: GenerationResult, query: str = None, category: str = "General",
                        temperature: float = 0.7, max_new_tokens: int = 100) -> str:
        """将轨迹以唯一文件名保存到 frontend/public/"""
        # 创建输出目录
        output_dir = Path("frontend/public/trajectories")
        output_dir.mkdir(parents=True, exist_ok=True)

        # 用时间戳生成唯一文件名
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = output_dir / f"trajectory_{timestamp}.json"
        
        # 提取用于可视化的注意力数据（仅输出 token）
        attention_matrix = []
        if result.attention_steps:
            for step in result.attention_steps:
                if step.attention_weights:
                    attention_matrix.append(step.attention_weights)
        
        # 按前端期望的格式组织数据
        trajectory_data = {
            "id": timestamp,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "test_case": {
                "category": category,
                "query": query or result.input_text,
                "description": f"Agent trajectory from {time.strftime('%Y-%m-%d %H:%M:%S')}"
            },
            "response": result.output_text,
            "tokens": result.tokens,
            "attention_data": {
                "tokens": result.tokens,
                "attention_matrix": attention_matrix,
                "num_layers": 1,  # 目前做了简化
                "num_heads": len(attention_matrix[0]) if attention_matrix and attention_matrix[0] else 0,
                "output_only": True,  # 标记：仅含输出 token 的注意力
                "context_length": result.context_length  # 输出 token 的起始位置
            },
            "metadata": {
                "model": self.model_name,
                "temperature": temperature,
                "max_tokens": max_new_tokens,
                "device": str(self.device),
                "attention_type": "output_only"  # 注明注意力类型
            }
        }
        
        # 保存到文件
        with open(filename, 'w') as f:
            json.dump(trajectory_data, f, indent=2, default=str)

        # 更新清单文件
        manifest_file = output_dir / "manifest.json"
        manifest = []
        if manifest_file.exists():
            try:
                with open(manifest_file, 'r') as f:
                    manifest = json.load(f)
            except Exception:
                manifest = []
        
        # 把新轨迹加入清单
        manifest.append({
            "filename": f"trajectory_{timestamp}.json",
            "id": timestamp,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": category,
            "query": query or result.input_text
        })
        
        # 清单只保留最近 50 条轨迹
        manifest = manifest[-50:]
        
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"Trajectory saved to {filename}")
        return str(filename)
    
    def generate_with_attention(
        self,
        prompt: str,
        max_new_tokens: int = 100,
        temperature: float = 0.7,
        top_p: float = 0.9,
        do_sample: bool = True,
        save_trajectory: bool = True,
        category: str = "General",
        store_full_tokens: bool = True
    ) -> GenerationResult:
        """
        生成文本并追踪注意力权重

        Args:
            prompt: 输入提示文本
            max_new_tokens: 最多生成的 token 数
            temperature: 采样温度
            top_p: 核采样参数
            do_sample: 是否使用采样
            store_full_tokens: 是否存储全部输入 token（不截断）

        Returns:
            包含 token 和注意力信息的 GenerationResult
        """
        # 对输入分词时不截断，保留全部 token
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=False)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        context_length = inputs['input_ids'].shape[1]
        
        # 解码输入 token——保存完整序列
        input_token_ids = inputs['input_ids'][0].tolist()
        input_tokens = [self.tokenizer.decode([tid], skip_special_tokens=False) for tid in input_token_ids]
        
        logger.info(f"Input: {len(input_tokens)} tokens")
        
        # 初始化追踪器
        self.tracker = AttentionTracker(self.tokenizer, context_length, self.verbose)

        # 配置生成参数
        generation_config = GenerationConfig(
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=do_sample,
            top_p=top_p,
            repetition_penalty=1.1
        )
        
        # 注册注意力钩子
        hooks = []
        hook_modules = []
        
        # 查找注意力模块
        for name, module in self.model.named_modules():
            if any(pattern in name.lower() for pattern in ['attn', 'attention', 'self_attn']):
                if hasattr(module, 'forward'):
                    hook = module.register_forward_hook(self._capture_attention_hook)
                    hooks.append(hook)
                    hook_modules.append(name)
                    
        if self.verbose:
            logger.info(f"Registered {len(hooks)} attention hooks")
            
        try:
            # 生成并追踪注意力
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    generation_config=generation_config,
                    logits_processor=LogitsProcessorList([self.tracker]),
                    output_attentions=True,
                    output_scores=True,
                    return_dict_in_generate=True
                )
                
            # 若可用，处理 generate 输出中的注意力
            if hasattr(outputs, 'attentions') and outputs.attentions is not None:
                self._process_generation_attentions(outputs.attentions, context_length)
                
        finally:
            # 移除钩子
            for hook in hooks:
                hook.remove()
                
        # 解码输出
        generated_ids = outputs.sequences[0][context_length:]
        output_text = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        # token 列表中保留特殊 token，确保准确呈现
        output_tokens = [self.tokenizer.decode([tid], skip_special_tokens=False) for tid in generated_ids.tolist()]
        
        # 获取注意力步骤
        attention_steps = self.tracker.get_attention_steps()
        
        logger.info(f"Generated {len(output_tokens)} tokens with {len(attention_steps)} attention steps")
        
        # 保存全部 token（输入 + 输出），构成完整序列
        all_token_ids = outputs.sequences[0].tolist()
        all_tokens = [self.tokenizer.decode([tid], skip_special_tokens=False) for tid in all_token_ids]
        
        result = GenerationResult(
            input_text=prompt,
            output_text=output_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens=all_tokens,  # 完整 token 序列
            attention_steps=attention_steps,
            context_length=context_length
        )
        
        # 如有要求则保存轨迹
        if save_trajectory:
            self.save_trajectory(result, query=prompt, category=category,
                                 temperature=temperature, max_new_tokens=max_new_tokens)
        
        return result
    
    def _process_generation_attentions(self, attentions, context_length):
        """处理生成输出中的注意力权重"""
        if not attentions or not self.tracker:
            return
            
        try:
            for step_idx, step_attentions in enumerate(attentions):
                if step_attentions is None or len(step_attentions) == 0:
                    continue
                    
                # 选择层
                layer_index = self.attention_layer_index
                if layer_index >= 0 and layer_index < len(step_attentions):
                    selected_attention = step_attentions[layer_index]
                elif layer_index < 0 and abs(layer_index) <= len(step_attentions):
                    selected_attention = step_attentions[layer_index]
                else:
                    selected_attention = step_attentions[-1]
                    
                if isinstance(selected_attention, torch.Tensor):
                    # 获取最后一个位置的注意力
                    current_seq_len = selected_attention.shape[2]
                    last_pos = current_seq_len - 1
                    
                    # 各头取平均
                    avg_attention = selected_attention[0, :, last_pos, :].mean(dim=0)

                    # 存入追踪器
                    seq_pos = context_length + step_idx
                    self.tracker.update_attention(seq_pos, avg_attention)
                    
        except Exception as e:
            if self.verbose:
                logger.warning(f"Error processing generation attentions: {e}")
    
    def chat(self, message: str, **kwargs) -> GenerationResult:
        """
        维护对话历史的聊天接口

        Args:
            message: 用户消息
            **kwargs: 生成参数

        Returns:
            带注意力追踪的 GenerationResult
        """
        # 加入对话历史
        self.conversation_history.append({"role": "user", "content": message})

        # 结合历史构建完整提示
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant."}
        ]
        messages.extend(self.conversation_history)
        
        # 应用聊天模板
        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        # 生成回复
        result = self.generate_with_attention(prompt, **kwargs)

        # 将助手回复加入历史
        self.conversation_history.append({
            "role": "assistant",
            "content": result.output_text
        })
        
        return result
    
    def reset_conversation(self):
        """重置对话历史"""
        self.conversation_history = []
        logger.info("Conversation history reset")


def demonstrate_attention_tracking():
    """演示注意力追踪功能"""
    print("=" * 60)
    print("Attention Visualization Demo")
    print("=" * 60)
    
    # 初始化 Agent
    agent = AttentionVisualizationAgent(verbose=True)

    # 带类别的测试提示
    test_prompts = [
        ("What is the capital of France?", "Knowledge"),
        ("Calculate 25 * 4 + 10", "Math"),
        ("Write a haiku about spring", "Creative"),
        ("If all cats are animals, and some animals are pets, can we conclude that all cats are pets?", "Reasoning"),
        ("Write a Python function to calculate factorial", "Code")
    ]
    
    results = []
    saved_files = []
    
    for i, (prompt, category) in enumerate(test_prompts, 1):
        print(f"\n--- Test {i}: {category} ---")
        print(f"Prompt: {prompt}")
        
        # 生成并追踪注意力，同时保存轨迹
        result = agent.generate_with_attention(
            prompt,
            max_new_tokens=100,
            temperature=0.7,
            save_trajectory=True,
            category=category
        )
        
        print(f"Response: {result.output_text}")
        print(f"Input tokens: {len(result.input_tokens)}")
        print(f"Output tokens: {len(result.output_tokens)}")
        print(f"Attention steps tracked: {len(result.attention_steps)}")
        
        results.append(result)
        time.sleep(1)  # 确保时间戳唯一
        
    return results


if __name__ == "__main__":
    results = demonstrate_attention_tracking()
    
    print("\n" + "=" * 60)
    print("✨ Demo Complete!")
    print("\n🌐 To view the visualizations:")
    print("   1. cd frontend")
    print("   2. npm install (if not already done)")
    print("   3. npm run dev")
    print("   4. Open http://localhost:3000")
    print("\n💾 Trajectories saved to frontend/public/trajectories/")
    print("=" * 60)
