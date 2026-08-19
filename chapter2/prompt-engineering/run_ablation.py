#!/usr/bin/env python3
"""
Tau-Bench 框架的消融实验运行器
通过测试不同变体来演示提示工程的重要性：
1. 语气变化（Trump 风格、休闲风格、默认风格）
2. wiki 规则随机化
3. 移除工具描述
"""

import argparse
import copy
import hashlib
import random
import os
import json
import shutil
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from tau_bench.types import RunConfig
# from litellm import provider_list  # 它返回的是枚举而非字符串
# 用字符串定义提供商选项
provider_list = ["openai", "anthropic", "azure", "bedrock", "cohere", "gemini", "groq", "mistral", "ollama", "openrouter", "replicate", "together_ai", "vertex_ai", "huggingface"]
from tau_bench.envs.user import UserStrategy

# 导入消融实验的自定义模块
from ablation_utils import (
    apply_tone_modification,
    load_randomized_wiki, 
    remove_tool_descriptions,
    ToneStyle
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "提示工程消融实验（实验 2-4）：基于 Tau-Bench 逐个降解提示工程要素，"
            "量化其对任务成功率的影响。\n"
            "三个消融维度：语气风格（--tone-style）、信息组织（--randomize-wiki）、"
            "工具描述（--remove-tool-descriptions）。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  # 基线（结构化提示词 + 完整工具描述 + 专业中立语气），跑前 10 个任务\n"
            "  python run_ablation.py --model gpt-5.6-luna --env airline --end-index 10\n\n"
            "  # 单个消融：打乱 wiki 规则的组织结构\n"
            "  python run_ablation.py --env airline --randomize-wiki --end-index 10\n\n"
            "  # 一键跑完整套消融并打印对比表（基线 + 各维度 + 全部叠加）\n"
            "  python run_ablation.py --env airline --all --end-index 10\n\n"
            "  # 跑完后单独汇总分析：python analyze_results.py\n"
        ),
    )

    # 原有参数
    parser.add_argument(
        "--num-trials", type=int, default=1,
        help="每个任务重复运行的次数（默认：1）"
    )
    parser.add_argument(
        "--env", type=str, choices=["retail", "airline"], default="airline",
        help="运行的场景环境：airline（航空客服）或 retail（零售客服），默认 airline"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-5.6-luna",
        help="The model to use for the agent (default: gpt-5.6-luna; routed via OpenRouter when OPENROUTER_API_KEY is set, else OpenAI direct)",
    )
    parser.add_argument(
        "--model-provider",
        type=str,
        choices=provider_list,
        default=None,  # 会根据模型自动设置
        help="The model provider for the agent (default: openai; a model id containing '/' auto-selects openrouter)",
    )
    parser.add_argument(
        "--user-model",
        type=str,
        default="gpt-5.6-luna",
        help="The model to use for the user simulator (default: gpt-5.6-luna; routed via OpenRouter when OPENROUTER_API_KEY is set, else OpenAI direct)",
    )
    parser.add_argument(
        "--user-model-provider",
        type=str,
        choices=provider_list,
        default=None,  # 会根据模型自动设置
        help="The model provider for the user simulator (default: openai; a model id containing '/' auto-selects openrouter)",
    )
    parser.add_argument(
        "--agent-strategy",
        type=str,
        default="tool-calling",
        choices=["tool-calling", "act", "react", "few-shot"],
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="The sampling temperature for the action model (default: 1.0 for gpt-5 compatibility)",
    )
    parser.add_argument(
        "--task-split",
        type=str,
        default="test",
        choices=["train", "test", "dev"],
    )
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--end-index", type=int, default=-1)
    parser.add_argument("--task-ids", type=int, nargs="+")
    parser.add_argument("--log-dir", type=str, default="results_ablation")
    parser.add_argument("--max-concurrency", type=int, default=1)
    parser.add_argument("--seed", type=int, default=10)
    parser.add_argument("--shuffle", type=int, default=0)
    parser.add_argument(
        "--max-agent-steps",
        type=int,
        default=30,
        help="每个任务允许的最大 Agent 步数（默认：30）",
    )
    parser.add_argument(
        "--protocol",
        type=str,
        default=str(Path(__file__).resolve().parent / "experiment_protocol.json"),
        help="冻结实验协议；--all 会复制并哈希到结果目录",
    )
    parser.add_argument(
        "--user-strategy", 
        type=str, 
        default="llm", 
        choices=[item.value for item in UserStrategy]
    )
    parser.add_argument("--few-shot-displays-path", type=str)
    
    # 消融实验新增参数
    parser.add_argument(
        "--tone-style",
        type=str,
        choices=["default", "trump", "casual"],
        default="default",
        help="维度一·语气风格：default（专业中立，基线）、trump（Trump 夸张风格）、casual（大量表情符号的休闲风格）"
    )

    parser.add_argument(
        "--randomize-wiki",
        action="store_true",
        help="维度二·信息组织：打乱 wiki 规则的组织结构（去除标题层次，规则平铺为无序列表）"
    )

    parser.add_argument(
        "--remove-tool-descriptions",
        action="store_true",
        help="维度三·工具描述：保留函数签名与参数，但移除所有描述性文本"
    )

    parser.add_argument(
        "--ablation-name",
        type=str,
        default="",
        help="本次消融实验的自定义名称（用于结果文件名标识）"
    )

    parser.add_argument(
        "--all",
        dest="run_all",
        action="store_true",
        help="一键运行完整消融套件（基线 + 各单维度 + 全部叠加），结束后打印成功率对比表"
    )

    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="（仅 --all 模式）将套件汇总统计写入该 JSON 文件路径（默认写入 log-dir/ablation_summary_<时间戳>.json）"
    )

    parser.add_argument(
        "--resume-from",
        type=str,
        default=None,
        help=(
            "Import only hash-valid, completed task receipts from a previous --all run directory. "
            "Accepted tasks are never regenerated; missing/error tasks run in the new log directory."
        ),
    )

    parser.add_argument(
        "--no-verbose",
        action="store_true",
        help="关闭详细输出（默认开启 verbose）"
    )

    args = parser.parse_args()
    
    # 设置 verbose 标志（默认 True，除非使用 --no-verbose）
    args.verbose = not args.no_verbose

    # 未指定时根据模型设置默认提供商。
    # 含 "/" 的模型 id（如 "openai/gpt-5"）是 OpenRouter 风格的 id，
    # 经 openrouter 路由（需要有效的 OPENROUTER_API_KEY）；裸 id
    # （如 "gpt-4o-mini"）走 OpenAI 直连（需要 OPENAI_API_KEY）。
    if args.model_provider is None:
        args.model_provider = "openrouter" if "/" in args.model else "openai"

    # 未指定时根据用户模拟器模型设置默认提供商
    if args.user_model_provider is None:
        args.user_model_provider = "openrouter" if "/" in args.user_model else "openai"

    # 通用兜底：若解析出的提供商是 OpenAI 直连但缺少 OPENAI_API_KEY、
    # 而存在 OPENROUTER_API_KEY，则把裸 gpt-* / o1-* id 经 OpenRouter 路由
    # （加前缀 "openai/"）。只要设置了 OPENAI_API_KEY，就保持默认的
    # （OpenAI 直连）行为不变。
    # gpt-5.x（含 gpt-5.6*）在直连 API 上需要 OpenAI 组织验证，因此
    # 只要存在 OPENROUTER_API_KEY，就把这些 id（以及缺 OPENAI_API_KEY 时
    # 的任何裸 gpt-*/o1-*）经 OpenRouter 路由（加前缀 "openai/"）。
    # 其余情况保持 OpenAI 直连行为不变。
    if os.environ.get("OPENROUTER_API_KEY"):
        no_openai = not os.environ.get("OPENAI_API_KEY")
        if args.model_provider == "openai" and (no_openai or args.model.lower().startswith("gpt-5")):
            args.model_provider = "openrouter"
            if "/" not in args.model:
                args.model = "openai/" + args.model
        if args.user_model_provider == "openai" and (no_openai or args.user_model.lower().startswith("gpt-5")):
            args.user_model_provider = "openrouter"
            if "/" not in args.user_model:
                args.user_model = "openai/" + args.user_model

    return args


def run_with_ablation(args):
    """在消融修改下运行 tau-bench"""

    # 导入原始 run 模块
    from tau_bench.run import run, agent_factory, display_metrics
    from tau_bench.envs import get_env
    import multiprocessing
    from concurrent.futures import ThreadPoolExecutor
    from typing import List
    from tau_bench.types import EnvRunResult

    # 创建配置
    config = RunConfig(
        model_provider=args.model_provider,
        user_model_provider=args.user_model_provider,
        model=args.model,
        user_model=args.user_model,
        num_trials=args.num_trials,
        env=args.env,
        agent_strategy=args.agent_strategy,
        temperature=args.temperature,
        task_split=args.task_split,
        start_index=args.start_index,
        end_index=args.end_index,
        task_ids=args.task_ids,
        log_dir=args.log_dir,
        max_concurrency=args.max_concurrency,
        seed=args.seed,
        shuffle=args.shuffle,
        user_strategy=args.user_strategy,
        few_shot_displays_path=args.few_shot_displays_path,
    )
    
    random.seed(config.seed)
    
    # 生成可读的日志文件名
    ablation_suffix = []
    if args.tone_style != "default":
        ablation_suffix.append(f"tone_{args.tone_style}")
    if args.randomize_wiki:
        ablation_suffix.append("wiki_random")
    if args.remove_tool_descriptions:
        ablation_suffix.append("no_tool_desc")
    if args.ablation_name:
        ablation_suffix.append(args.ablation_name)
    
    ablation_str = "_".join(ablation_suffix) if ablation_suffix else "baseline"
    
    time_str = datetime.now().strftime("%m%d%H%M%S")
    ckpt_path = f"{config.log_dir}/{config.agent_strategy}-{config.model.split('/')[-1]}-{ablation_str}_{time_str}.json"
    
    if not os.path.exists(config.log_dir):
        os.makedirs(config.log_dir)

    imported_results = []
    resume_receipt = None
    if args.resume_from:
        resume_dir = Path(args.resume_from).resolve()
        source_protocol = resume_dir / "experiment_protocol.json"
        current_protocol = Path(args.protocol).resolve()
        if not source_protocol.is_file() or source_protocol.read_bytes() != current_protocol.read_bytes():
            raise RuntimeError("resume source protocol does not match the frozen protocol")
        pattern = f"{config.agent_strategy}-{config.model.split('/')[-1]}-{ablation_str}_*.json"
        candidates = []
        expected_ablation = {
            "tone_style": args.tone_style,
            "randomize_wiki": args.randomize_wiki,
            "remove_tool_descriptions": args.remove_tool_descriptions,
        }
        for path in resume_dir.glob(pattern):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                source_config = payload.get("run_config", {})
                if any(source_config.get(key) != value for key, value in {
                    "model": config.model,
                    "user_model": config.user_model,
                    "model_provider": config.model_provider,
                    "user_model_provider": config.user_model_provider,
                    "env": config.env,
                    "seed": config.seed,
                    "task_ids": list(config.task_ids or []),
                }.items()):
                    continue
                if payload.get("ablation_config") != expected_ablation:
                    continue
                rows = payload.get("results", [])
            elif isinstance(payload, list):
                # 崩溃可能留下尚未包上最终元数据的逐任务追加式 checkpoint。
                # 此时直接按冻结命令校验每张回执，而不是重新生成
                # 已被接受的提供商调用。
                rows = payload
            else:
                continue
            accepted = []
            for row in rows:
                info = row.get("info", {})
                if row.get("task_id") not in list(config.task_ids or []) or not (
                    0 <= int(row.get("trial", -1)) < config.num_trials
                ):
                    continue
                calls = [
                    record
                    for source in ("agent_api_records", "user_api_records")
                    for record in (info.get(source) or [])
                ]
                successful = [record for record in calls if record.get("response")]
                receipt_ok = bool(successful) and all(
                    record["response"].get("id") and record["response"].get("usage")
                    and record.get("model") in {config.model, config.user_model}
                    and record.get("provider") in {
                        config.model_provider, config.user_model_provider
                    }
                    for record in successful
                ) and not info.get("error")
                if receipt_ok:
                    accepted.append(row)
            candidates.append((len(accepted), path.stat().st_mtime, path, accepted))
        if candidates:
            _count, _mtime, source_path, accepted = max(candidates)
            imported_results = [EnvRunResult.model_validate(row) for row in accepted]
            resume_receipt = {
                "source_path": str(source_path),
                "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                "imported_task_trials": sorted(
                    [[row.task_id, row.trial] for row in imported_results]
                ),
            }
    
    print(f"🔬 Running Ablation Study: {ablation_str}")
    print(f"  - Tone Style: {args.tone_style}")
    print(f"  - Randomize Wiki: {args.randomize_wiki}")
    print(f"  - Remove Tool Descriptions: {args.remove_tool_descriptions}")
    print(f"  - Checkpoint: {ckpt_path}")
    print()
    
    # 加载环境
    env = get_env(
        config.env,
        user_strategy=config.user_strategy,
        user_model=config.user_model,
        user_provider=config.user_model_provider,
        task_split=config.task_split,
        user_seed=config.seed,
    )
    
    # 应用消融修改
    modified_wiki = env.wiki
    modified_tools_info = env.tools_info

    # 1. 按需应用 wiki 随机化
    if args.randomize_wiki:
        print("📝 Using pre-randomized wiki rules...")
        modified_wiki = load_randomized_wiki(config.env)
    
    # 2. 按需应用语气修改
    if args.tone_style != "default":
        print(f"🎭 Applying {args.tone_style} tone style to system prompt...")
        tone_style = ToneStyle[args.tone_style.upper()]
        modified_wiki = apply_tone_modification(modified_wiki, tone_style)
    
    # 3. 按需移除工具描述
    if args.remove_tool_descriptions:
        print("🔧 Removing tool descriptions...")
        modified_tools_info = remove_tool_descriptions(modified_tools_info)
    
    # 用修改后的配置创建 Agent
    from ablation_agent import AblationAgent
    
    agent = AblationAgent(
        tools_info=modified_tools_info,
        wiki=modified_wiki,
        model=config.model,
        provider=config.model_provider,
        temperature=config.temperature,
        verbose=args.verbose,
        seed=config.seed,
    )
    
    # 运行任务
    end_index = (
        len(env.tasks) if config.end_index == -1 else min(config.end_index, len(env.tasks))
    )
    results: List[EnvRunResult] = list(imported_results)
    lock = multiprocessing.Lock()
    
    if config.task_ids and len(config.task_ids) > 0:
        print(f"Running tasks {config.task_ids}")
    else:
        print(f"Running tasks {config.start_index} to {end_index}")
    
    for i in range(config.num_trials):
        accepted_keys = {(row.task_id, row.trial) for row in imported_results}
        if config.task_ids and len(config.task_ids) > 0:
            idxs = [idx for idx in config.task_ids if (idx, i) not in accepted_keys]
        else:
            idxs = [
                idx for idx in range(config.start_index, end_index)
                if (idx, i) not in accepted_keys
            ]
        if config.shuffle:
            random.shuffle(idxs)
        
        def _run(idx: int) -> EnvRunResult:
            isolated_env = get_env(
                config.env,
                user_strategy=config.user_strategy,
                user_model=config.user_model,
                task_split=config.task_split,
                user_provider=config.user_model_provider,
                task_index=idx,
                user_seed=config.seed + i * 100000 + idx * 1000,
            )
            
            # 对隔离环境应用同样的修改
            if args.randomize_wiki:
                isolated_env.wiki = load_randomized_wiki(config.env)
            if args.tone_style != "default":
                isolated_env.wiki = apply_tone_modification(
                    isolated_env.wiki, 
                    ToneStyle[args.tone_style.upper()]
                )
            if args.remove_tool_descriptions:
                isolated_env.tools_info = remove_tool_descriptions(isolated_env.tools_info)
            
            print(f"Running task {idx}")
            try:
                res = agent.solve(
                    env=isolated_env,
                    task_index=idx,
                    max_num_steps=args.max_agent_steps,
                )
                result = EnvRunResult(
                    task_id=idx,
                    reward=res.reward,
                    info=res.info,
                    traj=res.messages,
                    trial=i,
                )
            except Exception as e:
                import traceback
                result = EnvRunResult(
                    task_id=idx,
                    reward=0.0,
                    info={
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                        "user_api_records": (
                            isolated_env.user.get_api_records()
                            if hasattr(isolated_env.user, "get_api_records") else []
                        ),
                    },
                    traj=[],
                    trial=i,
                )
            
            print(
                "✅" if result.reward == 1 else "❌",
                f"task_id={idx}",
                {
                    "reward": result.reward,
                    "metrics": result.info.get("experiment_metrics", {}),
                    "error": result.info.get("error"),
                },
            )
            print("-----")
            
            with lock:
                data = [row.model_dump() for row in imported_results]
                if os.path.exists(ckpt_path):
                    with open(ckpt_path, "r") as f:
                        data = json.load(f)
                with open(ckpt_path, "w") as f:
                    json.dump(data + [result.model_dump()], f, indent=2)
            return result
        
        with ThreadPoolExecutor(max_workers=config.max_concurrency) as executor:
            res = list(executor.map(_run, idxs))
            results.extend(res)
    
    display_metrics(results)
    
    # 保存带消融元数据的最终结果
    final_results = {
        "experiment_id": "2-4",
        "created_at": datetime.now().astimezone().isoformat(),
        "run_config": config.model_dump(),
        "ablation_config": {
            "tone_style": args.tone_style,
            "randomize_wiki": args.randomize_wiki,
            "remove_tool_descriptions": args.remove_tool_descriptions,
        },
        "resume_receipt": resume_receipt,
        "results": [result.model_dump() for result in results]
    }
    
    with open(ckpt_path, "w") as f:
        json.dump(final_results, f, indent=2)
        print(f"\n📄 Results saved to {ckpt_path}\n")
    
    args._last_checkpoint_path = ckpt_path
    return results


# 完整消融套件：(名称, {修改项})，覆盖书中描述的三个维度
# （实验 2-4）：语气 / 信息组织 / 工具描述。
ABLATION_SUITE = [
    ("baseline",      {"tone_style": "default", "randomize_wiki": False, "remove_tool_descriptions": False}),
    ("tone_trump",    {"tone_style": "trump",   "randomize_wiki": False, "remove_tool_descriptions": False}),
    ("tone_casual",   {"tone_style": "casual",  "randomize_wiki": False, "remove_tool_descriptions": False}),
    ("wiki_random",   {"tone_style": "default", "randomize_wiki": True,  "remove_tool_descriptions": False}),
    ("no_tool_desc",  {"tone_style": "default", "randomize_wiki": False, "remove_tool_descriptions": True}),
    ("all_ablations", {"tone_style": "casual",  "randomize_wiki": True,  "remove_tool_descriptions": True}),
]


def run_full_suite(args):
    """在进程内依次运行 ABLATION_SUITE 中的每个实验，然后打印一张
    对比表，让最终实验结果由单条命令产出。"""
    from analyze_results import (
        calculate_statistics,
        print_results_table,
        analyze_ablation_impact,
    )

    protocol_path = Path(args.protocol).resolve()
    protocol_bytes = protocol_path.read_bytes()
    protocol = json.loads(protocol_bytes)
    protocol_sha256 = hashlib.sha256(protocol_bytes).hexdigest()
    expected_task_ids = protocol["task_ids"]
    configured_task_ids = (
        list(args.task_ids)
        if args.task_ids
        else list(range(args.start_index, args.end_index))
    )
    if configured_task_ids != expected_task_ids:
        raise ValueError(
            f"Frozen protocol requires task IDs {expected_task_ids}; got {configured_task_ids}."
        )
    if args.model != protocol["model"] or args.user_model != protocol["user_model"]:
        raise ValueError("Model/user-model do not match the frozen protocol")
    if args.temperature != protocol["temperature"] or args.seed != protocol["seed"]:
        raise ValueError("Temperature/seed do not match the frozen protocol")
    if args.num_trials != protocol["trials_per_task"]:
        raise ValueError("Trial count does not match the frozen protocol")
    if args.max_agent_steps != protocol["max_agent_steps"]:
        raise ValueError("Agent step limit does not match the frozen protocol")

    Path(args.log_dir).mkdir(parents=True, exist_ok=True)
    copied_protocol = Path(args.log_dir) / "experiment_protocol.json"
    copied_protocol.write_bytes(protocol_bytes)

    suite_results = {}
    arm_artifacts = {}
    for name, mods in ABLATION_SUITE:
        args.tone_style = mods["tone_style"]
        args.randomize_wiki = mods["randomize_wiki"]
        args.remove_tool_descriptions = mods["remove_tool_descriptions"]
        # ablation_name 留空：run_with_ablation 已根据生效的开关推导出
        # 描述性后缀（如 "tone_trump"、"no_tool_desc"）。这里若设成
        # `name`，checkpoint 文件名里的后缀会翻倍
        # （如 "no_tool_desc_no_tool_desc"）。下方对比表以 ABLATION_SUITE
        # 的 `name` 为键，与文件名无关。
        args.ablation_name = ""

        print("\n" + "=" * 80)
        print(f"▶️  Running experiment: {name}")
        print("=" * 80)

        results = run_with_ablation(args)
        suite_results[name] = [float(r.reward) for r in results]
        checkpoint = Path(args._last_checkpoint_path)
        arm_artifacts[name] = {
            "path": str(checkpoint.resolve()),
            "sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        }

    # 跨全部技术做最终对比
    print_results_table(suite_results)
    analyze_ablation_impact(suite_results)

    # 持久化汇总结果
    output_path = args.output
    if not output_path:
        time_str = datetime.now().strftime("%m%d%H%M%S")
        output_path = f"{args.log_dir}/ablation_summary_{time_str}.json"
    if not os.path.exists(args.log_dir):
        os.makedirs(args.log_dir)
    arms = {}
    all_calls = []
    expected_results_per_arm = len(expected_task_ids) * args.num_trials
    for name, artifact in arm_artifacts.items():
        payload = json.loads(Path(artifact["path"]).read_text(encoding="utf-8"))
        results = payload["results"]
        calls = []
        metrics = []
        task_errors = []
        for result in results:
            info = result.get("info", {})
            if info.get("error"):
                task_errors.append({"task_id": result.get("task_id"), "error": info["error"]})
            metrics.append(info.get("experiment_metrics", {}))
            for source in ("agent_api_records", "user_api_records"):
                for record in info.get(source, []):
                    item = copy.deepcopy(record)
                    item["source"] = source
                    item["arm"] = name
                    item["task_id"] = result.get("task_id")
                    calls.append(item)
                    all_calls.append(item)

        successful_calls = [call for call in calls if call.get("response")]
        usage_complete = bool(successful_calls) and all(
            call["response"].get("id") and call["response"].get("usage")
            for call in successful_calls
        )
        no_transport_errors = all(not call.get("error") for call in calls)
        token_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        costs = []
        for call in successful_calls:
            usage = call["response"].get("usage") or {}
            for key in token_totals:
                token_totals[key] += int(usage.get(key) or 0)
            cost = call["response"].get("litellm_estimated_cost")
            if cost is not None:
                costs.append(float(cost))
        native_cost_cny = None
        if args.model == "kimi-k3" and usage_complete:
            pricing = protocol["pricing"]
            native_cost_cny = (
                token_totals["prompt_tokens"]
                * pricing["uncached_input_per_million_tokens"]
                / 1_000_000
                + token_totals["completion_tokens"]
                * pricing["output_per_million_tokens"]
                / 1_000_000
            )
        rewards = suite_results[name]
        arms[name] = {
            "artifact": artifact,
            "rewards": rewards,
            **calculate_statistics(rewards),
            "tasks_completed": len(results),
            "expected_tasks": expected_results_per_arm,
            "task_errors": task_errors,
            "agent_steps": [m.get("agent_steps") for m in metrics],
            "tool_calls": [m.get("tool_calls") for m in metrics],
            "tool_errors": [m.get("tool_errors") for m in metrics],
            "real_api_calls": len(successful_calls),
            "response_ids_present": usage_complete,
            "usage": token_totals,
            "observed_litellm_cost_usd": sum(costs),
            "all_calls_priced": len(costs) == len(successful_calls),
            "native_cost_cny": native_cost_cny,
            "arm_complete": (
                len(results) == expected_results_per_arm
                and not task_errors
                and no_transport_errors
                and usage_complete
            ),
        }

    configured_secrets = [
        os.environ.get(name)
        for name in ("OPENAI_API_KEY", "OPENROUTER_API_KEY")
        if os.environ.get(name)
    ]
    credential_findings = []
    for artifact in arm_artifacts.values():
        raw = Path(artifact["path"]).read_text(encoding="utf-8")
        if any(secret in raw for secret in configured_secrets):
            credential_findings.append(artifact["path"])

    campaign_complete = all(arm["arm_complete"] for arm in arms.values())
    summary = {
        "experiment_id": "2-4",
        "created_at": datetime.now().astimezone().isoformat(),
        "protocol_sha256": protocol_sha256,
        "protocol_copy": str(copied_protocol.resolve()),
        "provider": args.model_provider,
        "model": args.model,
        "user_model": args.user_model,
        "objective_scoring": "vendored tau-bench environment reward",
        "arms": arms,
        "credential_scan_passed": not credential_findings,
        "credential_findings": credential_findings,
        "usage_and_cost": {
            "total_real_api_calls": sum(arm["real_api_calls"] for arm in arms.values()),
            "prompt_tokens": sum(arm["usage"]["prompt_tokens"] for arm in arms.values()),
            "completion_tokens": sum(arm["usage"]["completion_tokens"] for arm in arms.values()),
            "total_tokens": sum(arm["usage"]["total_tokens"] for arm in arms.values()),
            "observed_litellm_cost_usd": sum(arm["observed_litellm_cost_usd"] for arm in arms.values()),
            "all_calls_priced": all(arm["all_calls_priced"] for arm in arms.values()),
            "native_cost_cny": sum(
                arm["native_cost_cny"] or 0 for arm in arms.values()
            ),
            "native_cost_complete": all(
                arm["native_cost_cny"] is not None for arm in arms.values()
            ),
            "qualification": protocol.get("pricing", {}).get(
                "qualification", "provider usage with LiteLLM response-cost estimate"
            ),
        },
        "campaign_complete": campaign_complete and not credential_findings,
        "hypothesis_results": {
            "historical_percentages_reproduced": False,
            "qualification": "Current fixed ten-task campaign only; compare arm metrics directly.",
        },
    }
    output_path = str(Path(output_path).resolve())
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    summary_hash = hashlib.sha256(Path(output_path).read_bytes()).hexdigest()
    manifest = {
        "experiment_id": "2-4",
        "campaign_complete": summary["campaign_complete"],
        "protocol_sha256": protocol_sha256,
        "summary_path": output_path,
        "summary_sha256": summary_hash,
        "arm_artifacts": arm_artifacts,
    }
    manifest_path = Path(args.log_dir) / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n📄 Suite summary saved to {output_path}\n")

    return suite_results


def main():
    args = parse_args()
    if args.run_all:
        run_full_suite(args)
    else:
        run_with_ablation(args)


if __name__ == "__main__":
    main()
