"""
消融实验专用 Agent
扩展 ToolCallingAgent 以支持语气风格修改
"""

import json
import os
import time
import copy
import traceback
from datetime import datetime, timezone
from litellm import completion
from typing import List, Optional, Dict, Any

from tau_bench.agents.base import Agent
from tau_bench.agents.tool_calling_agent import message_to_action
from tau_bench.envs.base import Env
from tau_bench.types import SolveResult, Action, RESPOND_ACTION_NAME


def completion_token_limit(model: str) -> int:
    """为思考型模型预留足够的输出预算，确保它能给出动作。"""
    return 8192 if "kimi-k3" in str(model).lower() else 4096


class AblationAgent(Agent):
    """
    支持语气风格修改的消融实验 Agent
    """
    
    def __init__(
        self,
        tools_info: List[Dict[str, Any]],
        wiki: str,
        model: str,
        provider: str,
        temperature: float = 0.0,
        verbose: bool = True,
        seed: Optional[int] = None,
    ):
        """
        初始化消融实验 Agent

        参数:
            tools_info: 可用工具的信息
            wiki: Wiki/系统提示词文本（可能已应用语气修改）
            model: 模型名
            provider: 模型提供商
            temperature: 采样温度
            verbose: 是否显示详细输出（默认: True）
        """
        self.tools_info = tools_info
        self.wiki = wiki
        self.model = model
        self.provider = provider
        self.temperature = temperature
        self.verbose = verbose
        self.seed = seed
    
    def solve(
        self, env: Env, task_index: Optional[int] = None, max_num_steps: int = 30
    ) -> SolveResult:
        """
        求解一个任务（可能带语气修改）

        参数:
            env: 环境
            task_index: 可选的任务索引
            max_num_steps: 最大步数

        返回:
            包含执行结果的 SolveResult
        """
        if self.verbose:
            print(f"\n{'='*80}")
            print(f"🎯 STARTING TASK {task_index if task_index is not None else 'N/A'}")
            print(f"{'='*80}")
            print(f"\n📜 SYSTEM PROMPT (Wiki) - {len(self.wiki)} characters:")
            print("─"*40)
            # 只展示 wiki 前 500 字符，便于查看语气修改
            if len(self.wiki) > 500:
                print(self.wiki[:500])
                print(f"... [{len(self.wiki) - 500} more characters]")
            else:
                print(self.wiki)
            print("─"*40)
        
        total_cost = 0.0
        env_reset_res = env.reset(task_index=task_index)
        obs = env_reset_res.observation
        info = env_reset_res.info.model_dump()
        reward = 0.0
        api_records: List[Dict[str, Any]] = []
        tool_call_count = 0
        tool_error_count = 0
        failure = None
        
        if self.verbose:
            print(f"\n📝 Initial User Message:")
            print(f"{'─'*40}")
            print(obs)
            print(f"{'─'*40}")
        
        # 初始化消息
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.wiki},
            {"role": "user", "content": obs},
        ]
        
        for step in range(max_num_steps):
            if self.verbose:
                print(f"\n{'━'*80}")
                print(f"📍 STEP {step + 1}/{max_num_steps}")
                print(f"{'━'*80}")
            
            # 调试：打印请求详情
            if self.verbose:  # verbose 时展示完整 API 请求详情
                print(f"\n{'='*60}")
                print(f"🚀 API CALL #{step + 1} to {self.provider} / {self.model}")
                print(f"{'='*60}")
                print(f"📤 SENDING {len(messages)} messages:")
                print("\n" + "─"*50)
                for i, msg in enumerate(messages):  # 展示全部消息
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    print(f"\n📨 Message [{i+1}] - Role: {role.upper()}")
                    print("─"*50)
                    if content:
                        print(content)
                    if 'tool_calls' in msg and msg['tool_calls']:
                        print(f"\n🔧 Tool Calls:")
                        for tc in msg['tool_calls']:
                            if isinstance(tc, dict):
                                print(f"  - Function: {tc.get('function', {}).get('name', 'unknown')}")
                                print(f"    Args: {tc.get('function', {}).get('arguments', 'none')}")
                    if 'tool_call_id' in msg:
                        print(f"\n🔧 Tool Response ID: {msg['tool_call_id']}")
                    print("─"*50)
                print("\n" + "="*60)
                print(f"🔧 Temperature: {self.temperature}")
                print(f"🛠️  Tools: {len(self.tools_info) if self.tools_info else 0} tools available")
                if self.tools_info:
                    print("\n📋 COMPLETE TOOL DEFINITIONS (JSON):")
                    print("─"*50)
                    import json
                    for i, tool in enumerate(self.tools_info, 1):
                        print(f"\n[Tool {i}] {tool.get('function', {}).get('name', 'unknown')}:")
                        print(json.dumps(tool, indent=2))
                    print("─"*50)
                print("="*60)
            
            # 调用模型获取补全
            try:
                # 准备补全参数
                # Kimi K3 在较长的 Tau-Bench 任务上可能把 4K 补全预算的大头
                # 花在隐藏思考上，然后返回一条无内容也无工具调用的空消息。
                # 这不是可用的 Agent 动作，曾让本已基本完成的 60 格实验
                # 在模拟器边界处失败。这里预留与配套 Kimi 用户模拟器相同的
                # 思考余量；普通非思考模型仍沿用历史限额。
                completion_limit = completion_token_limit(self.model)
                completion_kwargs = {
                    "messages": messages,
                    "model": self.model,
                    "custom_llm_provider": self.provider,
                    "tools": self.tools_info,
                    "temperature": self.temperature,
                    "max_tokens": completion_limit,
                }
                requested_seed = (
                    self.seed + (task_index or 0) * 1000 + step
                    if self.seed is not None else None
                )
                if requested_seed is not None:
                    completion_kwargs["seed"] = requested_seed
                
                # 为 gpt-5 加 reasoning_effort，尽量减少思考 token
                if "gpt-5" in self.model:
                    completion_kwargs["extra_body"] = {"reasoning_effort": "low"}
                    if self.verbose:
                        print("💭 Using reasoning_effort='low' to minimize thinking tokens")
                
                requested_at = datetime.now(timezone.utc).isoformat()
                started = time.perf_counter()
                res = completion(**completion_kwargs)
                choice = res.choices[0]
                usage = getattr(res, "usage", None)
                usage_payload = (
                    usage.model_dump()
                    if usage is not None and hasattr(usage, "model_dump")
                    else None
                )
                hidden_cost = getattr(res, "_hidden_params", {}).get("response_cost")
                api_records.append({
                    "requested_at": requested_at,
                    "provider": self.provider,
                    "model": self.model,
                    "task_index": task_index,
                    "step": step + 1,
                    "requested_seed": requested_seed,
                    "request": {
                        "messages": copy.deepcopy(messages),
                        "tools": copy.deepcopy(self.tools_info),
                        "temperature": self.temperature,
                        "max_tokens": completion_limit,
                    },
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                    "response": {
                        "id": getattr(res, "id", None),
                        "model": getattr(res, "model", None),
                        "created": getattr(res, "created", None),
                        "finish_reason": getattr(choice, "finish_reason", None),
                        "content": choice.message.content,
                        "reasoning_content": getattr(choice.message, "reasoning_content", None),
                        "tool_calls": [
                            item.model_dump() if hasattr(item, "model_dump") else item
                            for item in (getattr(choice.message, "tool_calls", None) or [])
                        ],
                        "usage": usage_payload,
                        "litellm_estimated_cost": hidden_cost,
                    },
                })
                
                # 调试：打印响应
                if self.verbose:  # verbose 时展示完整 API 响应详情
                    print(f"\n📥 RESPONSE received:")
                    print("─"*50)
                    if res.choices[0].message.content:
                        print("📝 Response Content:")
                        print("─"*50)
                        print(res.choices[0].message.content)  # 展示完整内容
                        print("─"*50)
                    if hasattr(res.choices[0].message, 'tool_calls') and res.choices[0].message.tool_calls:
                        print(f"\n🔧 Tool calls: {len(res.choices[0].message.tool_calls)} tool(s) called")
                        for idx, tc in enumerate(res.choices[0].message.tool_calls):  # 展示全部工具调用
                            print(f"\n  Tool Call [{idx+1}]:")
                            print(f"    - Function: {tc.function.name}")
                            print(f"    - Arguments (FULL):")
                            print(f"      {tc.function.arguments}")  # 展示完整参数
                    print(f"{'='*60}\n")
            except Exception as e:
                if "requested_at" in locals() and (
                    not api_records or api_records[-1].get("step") != step + 1
                ):
                    api_records.append({
                        "requested_at": requested_at,
                        "provider": self.provider,
                        "model": self.model,
                        "task_index": task_index,
                        "step": step + 1,
                        "requested_seed": requested_seed,
                        "request": completion_kwargs,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                        "error": {"type": type(e).__name__, "message": str(e)},
                    })
                print(f"\n❌ ERROR calling API:")
                print(f"  Provider: {self.provider}")
                print(f"  Model: {self.model}")
                print(f"  Error: {str(e)}")
                print(f"  Error type: {type(e).__name__}")
                print(f"  Traceback:\n{traceback.format_exc()}")
                failure = {
                    "type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }
                # 返回一个计 0 分的失败结果，同时保留所有已确认的调用回执。
                # 之前在这里直接抛异常会让外层 runner 丢弃完整的内存轨迹
                # 以及晚期错误发生前已完成的全部调用。
                reward = 0.0
                break
            
            next_message = res.choices[0].message.model_dump()
            cost = res._hidden_params.get("response_cost", 0)
            if cost is not None:
                total_cost += cost
            
            # verbose 时展示 assistant 响应
            if self.verbose:
                print(f"\n🤖 Assistant Response:")
                print(f"{'─'*40}")
                if next_message.get("content"):
                    print(f"💬 Message: {next_message['content']}")
                if next_message.get("tool_calls"):
                    print(f"\n🔧 Tool Calls ({len(next_message['tool_calls'])} tool(s)):")
                    for i, tc in enumerate(next_message["tool_calls"], 1):
                        func_name = tc.get('function', {}).get('name', 'unknown')
                        func_args = tc.get('function', {}).get('arguments', '')
                        print(f"  [{i}] {func_name}")
                        try:
                            import json
                            args_dict = json.loads(func_args) if isinstance(func_args, str) else func_args
                            for key, value in args_dict.items():
                                value_str = str(value)
                                print(f"      • {key}: {value_str}")
                        except Exception:
                            print(f"      Args: {func_args}")
                print(f"{'─'*40}")
            
            
            # 把消息转换为动作
            action = message_to_action(next_message)
            if action.name != RESPOND_ACTION_NAME:
                tool_call_count += 1
            
            # 在环境中执行一步
            env_response = env.step(action)
            if action.name != RESPOND_ACTION_NAME and str(
                env_response.observation
            ).startswith(("Error:", "Unknown action")):
                tool_error_count += 1
            reward = env_response.reward
            info = {**info, **env_response.info.model_dump()}
            
            # verbose 时展示环境响应
            if self.verbose:
                print(f"\n🌍 Environment Response:")
                print(f"{'─'*40}")
                print(f"  Action: {action.name}")
                if env_response.observation:
                    obs_str = env_response.observation
                    if action.name != RESPOND_ACTION_NAME:
                        print(f"  Tool Output: {obs_str}")
                    else:
                        print(f"  User Reply: {obs_str}")
                print(f"  Reward: {reward}")
                print(f"  Done: {env_response.done}")
                print(f"{'─'*40}")
            
            # 按动作类型更新消息
            if action.name != RESPOND_ACTION_NAME:
                # 工具调用 —— 只保留第一个工具调用
                next_message["tool_calls"] = next_message["tool_calls"][:1]
                messages.extend(
                    [
                        next_message,
                        {
                            "role": "tool",
                            "tool_call_id": next_message["tool_calls"][0]["id"],
                            "name": next_message["tool_calls"][0]["function"]["name"],
                            "content": env_response.observation,
                        },
                    ]
                )
            else:
                # 回复用户
                messages.extend(
                    [
                        next_message,
                        {"role": "user", "content": env_response.observation},
                    ]
                )
            
            # 检查是否结束
            if env_response.done:
                if self.verbose:
                    if reward == 1:
                        print(f"\n✅ Task completed successfully! (Reward = {reward})")
                    else:
                        print(f"\n🏁 Task ended (Reward = {reward})")
                break
        
        if self.verbose:
            print(f"\n{'='*80}")
            print(f"📊 TASK SUMMARY")
            print(f"{'='*80}")
            print(f"  Final Reward: {reward}")
            print(f"  Total Steps: {step + 1}")
            print(f"  Total Cost: ${total_cost:.4f}")
            print(f"  Messages Exchanged: {len(messages)}")
            print(f"{'='*80}\n")

        info["experiment_metrics"] = {
            "agent_steps": step + 1,
            "agent_model_calls": len(api_records),
            "tool_calls": tool_call_count,
            "tool_errors": tool_error_count,
        }
        info["agent_api_records"] = api_records
        info["user_api_records"] = (
            env.user.get_api_records()
            if hasattr(env.user, "get_api_records") else []
        )
        if failure is not None:
            info["error"] = failure["message"]
            info["error_type"] = failure["type"]
            info["traceback"] = failure["traceback"]
        
        return SolveResult(
            reward=reward,
            info=info,
            messages=messages,
            total_cost=total_cost,
        )
