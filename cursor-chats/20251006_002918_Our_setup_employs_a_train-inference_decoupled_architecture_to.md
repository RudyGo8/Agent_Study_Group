# Cursor Chat: ai-agent-book

## Metadata
- **Project**: ai-agent-book
- **Path**: `/Users/boj`
- **Date**: 2025-10-06 00:29:18
- **Session ID**: `d34d50ae-1298-4cdd-80cf-754ccc8a1d94`

## Conversation

### 👤 You

Our setup employs a train-inference decoupled architecture to optimize resource
utilization for agent training. The training process runs on a dedicated node featuring 8 NVIDIA A100 (80GB)
GPUs and a 96-core CPU. This node is allocated 1200GB of system memory to support memory-intensive
optimization strategies such as DeepSpeed ZeRO3 (Rajbhandari et al., 2020). A separate, parallel node
is dedicated to environment interaction and rollout generation. This inference node is equipped with an
identical set of 8 NVIDIA A100 GPUs and a 96-core CPU, but is configured with 800GB of system memory,
which is ample for high-throughput agent inference.

Given the established need for large-scale data generation, this section evaluates the core efficiency of
AWORLD. We measure the wall-clock time for a full cycle of experience generation and model training,
comparing our distributed approach against a standard single-node setup.
One might ask why the single-node baseline is sequential rather than parallel. A naive parallel implementation on a single node is not a viable baseline for complex environments like GAIA. The combination of
resource-intensive tools (e.g., a full browser engine) and long-horizon tasks creates significant CPU and memory demands. Attempting to run multiple such rollouts concurrently on one machine leads to severe resource
contention and process instability, making sequential execution the only stable and practical configuration for
a single-node setup and a fair point of comparison.
As shown in Table 2, the efficiency gains are substantial. The AWORLD Executor completes the rollout phase
in just 525 seconds, while the Sequential Executor requires 7695 seconds. This translates to a 14.6-fold
speedup in experience generation. Crucially, as the training time (144s) is constant, the total cycle time
is reduced from 7839 seconds to a mere 669 seconds. This result provides clear quantitative evidence for
a central thesis of our work: for complex agentic tasks, the primary bottleneck has shifted from training
computation to environmental interaction. AWORLD is purpose-built to dismantle this bottleneck, making it an
indispensable tool for the scalable “learning from practice” paradigm.

--
Read the AWorld code repo in week7, the train folder. Where did the code implement the distributed inference?

---

### 🤖 Cursor Assistant

I'll scan the `projects/week7/AWorld` codebase to find where training/inference decoupling, rollout executors, and DeepSpeed ZeRO3 are implemented, then narrow to the `train` folder.

---

### 🤖 Cursor Assistant

I'll look for where decoupled inference/training, rollout executors, and any DeepSpeed/ZeRO or parallel vs sequential executors are implemented specifically under `projects/week7/AWorld/train`. Then I’ll broaden to the rest of AWorld if needed to locate executors and runtime separation.

---

### 🤖 Cursor Assistant

I'll search the training folder for concrete hooks: (1) decoupled vLLM server/client and async rollouts, (2) configs for FSDP/DeepSpeed/ZeRO, and (3) any sequential vs parallel executors or benchmarking scripts.

---

### 🤖 Cursor Assistant

I scanned `projects/week7/AWorld/train` and the connected runtime code to pinpoint where each claim is implemented.

### Decoupled training vs inference (vLLM server + agent rollouts)
- Trainer switches to remote inference (“server” mode) and delegates rollouts to AWORLD agents:
```21:33:projects/week7/AWorld/train/adapter/swift/aworld_agent_trainer.py
class AworldTrainer(GRPOTrainer):
    def _engine_infer(
            self,
            infer_requests: InputsType,
            request_config: Optional[RequestConfig] = None,
            *,
            use_tqdm: Optional[bool] = False,
    ) -> List[ChatCompletionResponse]:
        with profiling_context(self, 'generate'):
            if self.vllm_mode != 'server':
                return self.engine.infer(infer_requests, request_config, use_tqdm=use_tqdm)
```
```47:66:projects/week7/AWorld/train/adapter/swift/aworld_agent_trainer.py
    def run_infer(self, infer_requests: List[Dict[str, Any]]) -> List[ChatCompletionResponse]:
        workers = [asyncio.create_task(self._rollout(req)) for req in infer_requests]
        results = sync_exec(asyncio.gather, *workers)
        return self.convert_agent_output(results, infer_requests)

    async def _rollout(self, req: Dict[str, Any]):
        agent = self.build_agents()
        result = await self.run_agents(req, agent)
        return result

    async def run_agents(self, input, agent):
        # collect trajectory
        if isinstance(agent, Swarm):
            result = Runners.sync_run(input=input, swarm=agent)
        else:
            result = Runners.sync_run(input=input, agent=agent)
        return result
```
- Training launch config explicitly uses the vLLM rollout server in async mode and multi-node settings:
```1:12:projects/week7/AWorld/train/examples/train_gaia_with_aworld_verl/run.sh
#!/usr/bin/env bash
set -xeuo pipefail

# ================= cluster topology =================
export GPUS_PER_NODE=${SLURM_GPUS_ON_NODE:-${GPUS_PER_NODE:-1}}  # GPUs on this node
NNODES=${SLURM_JOB_NUM_NODES:-${NNODES:-1}}
export NNODES
export RAY_NUM_NODES=$NNODES

echo "Using $NNODES nodes and $GPUS_PER_NODE GPUs per node..."
```
```113:139:projects/week7/AWorld/train/examples/train_gaia_with_aworld_verl/run.sh
    actor_rollout_ref.ref.log_prob_max_token_len_per_gpu=$log_prob_max_token_len_per_gpu \
    actor_rollout_ref.rollout.name=vllm \
    actor_rollout_ref.rollout.mode=async \
    actor_rollout_ref.rollout.tensor_model_parallel_size=$infer_tp \
    actor_rollout_ref.rollout.multi_turn.max_user_turns=$max_turns \
    actor_rollout_ref.rollout.multi_turn.max_assistant_turns=$max_turns \
    actor_rollout_ref.rollout.multi_turn.format=hermes \
    actor_rollout_ref.rollout.agent.agent_loop_config_path=$agent_loop_config_path \
    actor_rollout_ref.rollout.gpu_memory_utilization=0.75 \
    actor_rollout_ref.rollout.n=$n_resp_per_prompt \
    actor_rollout_ref.rollout.val_kwargs.top_p=0.6 \
    actor_rollout_ref.rollout.val_kwargs.temperature=1.0 \
    actor_rollout_ref.rollout.val_kwargs.n=$n_resp_per_prompt_val \
    actor_rollout_ref.rollout.multi_turn.tool_config_path=$dummy_tool_config_path \
    custom_reward_function.path="${reward_fn_file_path}"\
    custom_reward_function.name="${reward_fn_name}"\
    trainer.logger=console \
    trainer.project_name=$project_name \
    trainer.experiment_name=$experiment_name \
    trainer.n_gpus_per_node="$GPUS_PER_NODE" \
    trainer.val_before_train=true \
    trainer.log_val_generations=50 \
    trainer.nnodes="$NNODES" \
    trainer.save_freq=-1 \
    trainer.default_local_dir="$default_local_dir" \
    trainer.test_freq=5 \
    trainer.total_epochs=1 "$@"
```
- The VERL adapter pulls model/server info and rollout parameters from config (ties into vLLM server mode):
```35:39:projects/week7/AWorld/train/adapter/verl/aworld_agent_loop.py
    async def get_llm_server_model_name(self):
        model_name = "/".join(self.config.actor_rollout_ref.model.path.split("/")[-2:])
        logger.info(f"get_server_model_name#model_name: {model_name}")
        return model_name
```
```198:202:projects/week7/AWorld/train/adapter/verl/aworld_agent_loop.py
        response_length = self.config.actor_rollout_ref.rollout.response_length
        prompt_ids, response_ids, response_mask = await encode_messages(self.tokenizer,
                                                                        messages,
```

### Parallel rollout executor vs sequential baseline
- Trainer runs multiple rollouts concurrently via `asyncio.create_task` (AWORLD Executor = parallel rollout generation):
```47:52:projects/week7/AWorld/train/adapter/swift/aworld_agent_trainer.py
    def run_infer(self, infer_requests: List[Dict[str, Any]]) -> List[ChatCompletionResponse]:
        workers = [asyncio.create_task(self._rollout(req)) for req in infer_requests]
        results = sync_exec(asyncio.gather, *workers)
```
- Task execution layer supports parallel vs serial via config flag; serial is the sequential baseline:
```151:162:projects/week7/AWorld/aworld/utils/run_util.py
async def exec_tasks(tasks: List[Task], run_conf: RunConfig = RunConfig()) -> Dict[str, TaskResponse]:
    final_tasks = []
    # task list sequence-dependent execution
    if run_conf and run_conf.sequence_dependent:
        return await serial_exec_tasks(tasks=tasks, run_conf=run_conf)

    for task in tasks:
        if not task.group_id:
            task.group_id = uuid.uuid4().hex
        final_tasks.append(task)
    runners = await choose_runners(final_tasks)
    return await execute_runner(runners, run_conf)
```
- Local runtime executes multiple runners concurrently (coroutines + process pool), underpinning parallel rollouts:
```92:116:projects/week7/AWorld/aworld/runners/runtime_engine.py
    async def execute(self, funcs: List[Callable[..., Any]], *args, **kwargs) -> Dict[str, Any]:
        # opt of the one task process
        if self.conf.get('reuse_process', True):
            results = {}
            coroutine_funcs = []
            sync_funcs = []
            for func in funcs:
                if inspect.iscoroutinefunction(func):
                    coroutine_funcs.append(func(*args, **kwargs))
                else:
                    sync_funcs.append(func)

            for func in sync_funcs:
                try:
                    res = func(*args, **kwargs)
                    results[res.id] = res
```
```128:135:projects/week7/AWorld/aworld/runners/runtime_engine.py
        try:
            with ProcessPoolExecutor(num_process) as pool:
                for func in funcs:
                    futures.append(pool.submit(RuntimeEngine.func_wrapper, func, *args, **kwargs))
```
- A strictly sequential agent path is also available for baseline scenarios:
```14:22:projects/week7/AWorld/aworld/agents/serial_llm_agent.py
class SerialableAgent(Agent):
    """Support for serial execution of agents based on dependency relationships in the swarm.

    The parameters of the extension function are the agent itself, which can obtain internal information of the agent.
    `aggregate_func` function example:
    >>> def agg(agent: SerialableAgent, res: Dict[str, Any]) -> ActionModel:
    >>>     ...
    >>>     return ActionModel(agent_name=agent.id(), policy_info='...')
```
```32:49:projects/week7/AWorld/aworld/agents/serial_llm_agent.py
    async def async_policy(self, observation: Observation, info: Dict[str, Any] = {}, **kwargs) -> List[ActionModel]:
        
        results = {}
        action = ActionModel(agent_name=self.id(), policy_info=observation.content)
        if self.agents:
            for agent in self.agents:
                result = await exec_agent(observation.content, agent, self.context, sub_task=True)
                if result:
                    if result.success:
                        con = result.answer
                    else:
                        con = result.msg
                    action = ActionModel(agent_name=agent.id(), policy_info=con)
                    observation = self._action_to_observation(action, agent.id())
                    results[agent.id()] = con
```

### Distributed execution backends and isolation
- Runtime supports multiple engines (local, spark, ray, k8s), and the executor selection bridges to the chosen backend:
```17:21:projects/week7/AWorld/aworld/runners/runtime_engine.py
LOCAL = "local"
SPARK = "spark"
RAY = "ray"
K8S = "k8s"
```
```60:79:projects/week7/AWorld/aworld/runners/utils.py
    name = run_conf.engine_name
    if run_conf.cls:
        runtime_backend = new_instance(run_conf.cls, run_conf)
    else:
        runtime_backend = new_instance(
            f"aworld.runners.runtime_engine.{snake_to_camel(name)}Runtime", run_conf)
    runtime_engine = runtime_backend.build_engine()

    if run_conf.engine_name != EngineName.LOCAL or run_conf.reuse_process == False:
        # distributed in AWorld, the `context` can't carry by response
        for runner in runners:
            if not isinstance(runner, TaskRunner):
                logger.info("not task runner in AWorld, skip...")
                continue
            if runner.task.conf:
                runner.task.conf.resp_carry_context = False
            else:
                runner.task.conf = ConfigDict(resp_carry_context=False)
    return await runtime_engine.execute([runner.run for runner in runners])
```

### Timing/wall‑clock measurement hook
- Training stage uses TRL’s profiling context to measure “generate” (rollout) wall‑clock time:
```28:33:projects/week7/AWorld/train/adapter/swift/aworld_agent_trainer.py
    ) -> List[ChatCompletionResponse]:
        with profiling_context(self, 'generate'):
            if self.vllm_mode != 'server':
                return self.engine.infer(infer_requests, request_config, use_tqdm=use_tqdm)
```

### Memory optimization config (FSDP/offload; Ulysses)
- This repo exposes FSDP offload and Ulysses sequence parallel settings; deepspeed is listed as a dependency in the docs, but ZeRO3 configuration itself is not defined here (it’s handled by VERL/underlying trainer):
```108:112:projects/week7/AWorld/train/examples/train_gaia_with_aworld_verl/run.sh
    actor_rollout_ref.actor.ppo_mini_batch_size=$ppo_mini_batch_size \
    actor_rollout_ref.actor.ppo_max_token_len_per_gpu=$actor_max_token_len_per_gpu \
    actor_rollout_ref.actor.ulysses_sequence_parallel_size=$train_sp \
    actor_rollout_ref.actor.fsdp_config.param_offload=$offload \
    actor_rollout_ref.actor.fsdp_config.optimizer_offload=$offload \
```
```30:34:projects/week7/AWorld/train/README.md
-   Install a PyTorch version that matches your CUDA version. You can find the command on the [PyTorch website](https://pytorch.org/get-started/locally/).
3.  **Install Verl and Dependencies**:
    -   When you install Verl (e.g., via `pip install -e .`), other Python packages like `transformers`, `deepspeed`, and `vllm` will be installed automatically.
    -   **Important**: This step requires the prerequisites from steps 1 and 2 to succeed, as some packages need to be compiled against CUDA. See `setup.py` for a full dependency list.
```

### Where the “single‑node sequential baseline” comes from
- Achieved by setting `RunConfig.sequence_dependent=True`, which forces `serial_exec_tasks` instead of the parallel path (no special class named “Sequential Executor” is required):
```151:156:projects/week7/AWorld/aworld/utils/run_util.py
async def exec_tasks(tasks: List[Task], run_conf: RunConfig = RunConfig()) -> Dict[str, TaskResponse]:
    final_tasks = []
    # task list sequence-dependent execution
    if run_conf and run_conf.sequence_dependent:
        return await serial_exec_tasks(tasks=tasks, run_conf=run_conf)
```

- For completeness, the docs also show sequential vs parallel swarm topologies:
```7:18:projects/week7/AWorld/docs/Quickstart/workflow_construction.md
### Sequential
"""
Sequential Agent Pipeline: agent1 → agent2 → agent3

Executes agents in sequence where each agent's output becomes 
the next agent's input, enabling multi-step collaborative processing.
"""
swarm = Swarm([(agent1, agent2), (agent2, agent3)], root_agent=[agent1])
result: TaskResponse = Runners.run(input=question, swarm=swarm)
```
```20:35:projects/week7/AWorld/docs/Quickstart/workflow_construction.md
### Parallel
"""
Parallel Agent Execution with Barrier Synchronization

    Input ──┬─→ agent1 ──┐
            │            ├──→ agent3 (barrier wait)
            └─→ agent2 ──┘

- agent1 and agent2 execute in parallel
- agent3 acts as a barrier, waiting for both agents
- agent3 processes combined outputs from agent1 and agent2
"""
swarm = Swarm([(agent1, agent3), (agent2, agent3)], root_agent=[agent1, agent2])
result: TaskResponse = Runners.run(input=question, swarm=swarm)
```

### Net: how the paper’s claims map to code
- Train/inference decoupling: vLLM server mode + AWORLD agent rollouts in trainer; multi‑node launch flags in `run.sh`.
- Parallel rollouts: asyncio parallelism at trainer level + runtime’s concurrent execution; sequential baseline via `sequence_dependent`.
- Time measurement: TRL profiling in `_engine_infer('generate')`.
- Memory efficiency: FSDP offload + Ulysses exposed here; ZeRO3 is referenced in docs (installed with VERL) but not configured in this repo’s scripts (handled by VERL’s trainer configs).

I can point you to any missing config (e.g., VERL’s ZeRO3 YAML) if you want to wire ZeRO explicitly into this run.

- I found and cited the trainer hooks, rollout concurrency, runtime backends, and configs. If you want, I’ll extract the exact `RunConfig` knobs to flip between sequential and parallel for a quick A/B run.

---

### 🤖 Cursor Assistant

I'll help you find where the distributed inference is implemented in the AWorld code. Let me start by exploring the train folder structure.

---

### 🤖 Cursor Assistant

Let me search for where VeRL's distributed inference is configured and how the separate inference node is utilized.

---

### 🤖 Cursor Assistant

Let me check if there's VeRL-related documentation or code that shows the distributed inference implementation.

---

### 🤖 Cursor Assistant

Let me look at how the async mode works and how multiple nodes are coordinated.

---

### 🤖 Cursor Assistant

Based on my exploration of the AWorld code repository, I can now explain where and how the distributed inference is implemented.

## Key Finding: Distributed Inference is Implemented in VeRL Framework

The distributed inference mentioned in the paper (the "AWORLD Executor" with train-inference decoupled architecture) is **not directly implemented in AWorld's `train/` folder**. Instead, **AWorld leverages the VeRL framework** for this functionality.

## Architecture Overview

Here's how it works:

### 1. **Integration Point: `train/adapter/verl/aworld_agent_loop.py`**
AWorld integrates with VeRL through the `AworldAgentLoop` class, which:
- Inherits from VeRL's `AgentLoopBase`
- Manages the connection to LLM servers running on separate inference nodes
- Gets server addresses dynamically via `get_llm_server_address()`

```python:29:42:projects/week7/AWorld/train/adapter/verl/aworld_agent_loop.py
    async def get_llm_server_address(self, server_name: str = None) -> str:
        server = self.server_manager._choose_server(server_name or uuid.uuid4().hex)
        base_url = await server.get_server_address.remote()
        base_url = f"http://{base_url}/v1"
        logger.info(f"get_server_address#base_url: {base_url}")
        return base_url
```

### 2. **Configuration: `run.sh` enables async mode**
The distributed inference is enabled via configuration:

```bash:114:115:projects/week7/AWorld/train/examples/train_gaia_with_aworld_verl/run.sh
    actor_rollout_ref.rollout.name=vllm \
    actor_rollout_ref.rollout.mode=async \
```

### 3. **VeRL's Distributed Infrastructure**

The actual distributed inference is implemented in **VeRL** (`projects/week7/verl/`):

#### a) **`verl/workers/rollout/replica.py`** - Rollout Modes
Defines three rollout modes:
- **HYBRID**: Rollout and training share GPUs (sequential)
- **COLOCATED**: Same placement group, separate processes  
- **STANDALONE**: Separate GPU resources across nodes ✅ (This is what the paper describes)

```python:50:52:projects/week7/verl/verl/workers/rollout/replica.py
    # Standalone rollout server with separate GPU resource, disaggregated architecture.
    # Usage scenarios: off-policy training.
    STANDALONE = "standalone"
```

#### b) **`verl/workers/rollout/vllm_rollout/vllm_async_server.py`** - Server Management
- **`vLLMHttpServer`**: Creates vLLM inference servers on separate nodes
- **`ExternalZeroMQDistributedExecutor`**: Uses ZeroMQ for communication between training and inference nodes
- Supports multi-node deployment (configured via `nnodes` parameter)

```python:110:137:projects/week7/verl/verl/workers/rollout/vllm_rollout/vllm_async_server.py
@ray.remote(num_cpus=1)
class vLLMHttpServer:
    """vLLM http server in single node, this is equivalent to launch server with command line:
    ```
    vllm serve --tensor-parallel-size=8 ...
    ```
    """

    def __init__(
        self,
        config: RolloutConfig | RewardModelConfig,
        model_config: HFModelConfig,
        rollout_mode: RolloutMode,
        workers: list[ActorHandle],
        replica_rank: int,
        node_rank: int,
        gpus_per_node: int,
        nnodes: int,
    ):
        """
        Args:
            config (RolloutConfig | RewardModelConfig): full config.
            model_config (HFModelConfig): model config.
            rollout_mode (RolloutMode): rollout mode.
            replica_rank (int): replica rank, a replica may contain multiple nodes.
            node_rank (int): node rank.
            gpus_per_node (int): number of gpus per node.
            nnodes (int): number of nodes.
```

#### c) **`verl/experimental/agent_loop/agent_loop.py`** - Load Balancing
- **`AsyncLLMServerManager`**: Manages multiple LLM servers
- Implements load balancing across inference nodes
- Supports sticky sessions for prefix caching

```python:48:83:projects/week7/verl/verl/experimental/agent_loop/agent_loop.py
class AsyncLLMServerManager:
    """
    A class to manage multiple OpenAI compatible LLM servers. This class provides
    - Load balance: least requests load balancing
    - Sticky session: send multi-turn chat completions to same server for automatic prefix caching
    """

    def __init__(self, config: DictConfig, server_handles: list[ray.actor.ActorHandle], max_cache_size: int = 10000):
        """Initialize the AsyncLLMServerManager.

        Args:
            config (DictConfig): YAML config.
            server_handles (List[ray.actor.ActorHandle]): OpenAI compatible LLM server actor handles.
            max_cache_size (int, optional): max cache size for request_id to server mapping. Defaults to 10000.
        """
        self.config = config
        self.server_handles = server_handles
        random.shuffle(self.server_handles)

        # Least requests load balancing
        self.weighted_serveres = [[0, (hash(server), server)] for server in server_handles]
        heapq.heapify(self.weighted_serveres)

        # LRU cache to map request_id to server
        self.request_id_to_server = LRUCache(maxsize=max_cache_size)

    def _choose_server(self, request_id: str) -> ray.actor.ActorHandle:
        # TODO: implement server pressure awareness load balancing
        if request_id in self.request_id_to_server:
            return self.request_id_to_server[request_id]

        server = self.weighted_serveres[0][1][1]
        self.weighted_serveres[0][0] += 1
        heapq.heapreplace(self.weighted_serveres, self.weighted_serveres[0])
        self.request_id_to_server[request_id] = server
        return server
```

### 4. **Ray Framework for Distribution**
VeRL uses **Ray** for distributed execution across nodes:

```bash:7:9:projects/week7/AWorld/train/examples/train_gaia_with_aworld_verl/run.sh
NNODES=${SLURM_JOB_NUM_NODES:-${NNODES:-1}}
export NNODES
export RAY_NUM_NODES=$NNODES
```

## Summary

The **distributed inference** is implemented through:

1. **VeRL's async rollout mode** (`actor_rollout_ref.rollout.mode=async`)
2. **Separate Ray resource pools** for training and inference nodes
3. **vLLM servers** launched on dedicated inference nodes
4. **AsyncLLMServerManager** for load balancing requests
5. **ZeroMQ communication** between training and inference processes

AWorld's contribution is the **adapter layer** (`train/adapter/verl/`) that bridges AWorld agents with VeRL's distributed training infrastructure, enabling the 14.6x speedup mentioned in the paper by parallelizing environment interaction across dedicated inference nodes.

---

### 👤 You

How to configure the remote vllm server in this mode

---

### 🤖 Cursor Assistant

Let me find the specific configuration details for setting up the remote vLLM server in async mode.

---

### 🤖 Cursor Assistant

Based on my analysis of the AWorld and VeRL code, here's a comprehensive guide on **how to configure the remote vLLM server in async distributed inference mode**:

## Configuration Overview

The distributed inference uses **VeRL's async rollout mode** with **Ray** for distributed orchestration. Here's how to set it up:

---

## 1. **Ray Cluster Setup (Multi-Node)**

First, set up a Ray cluster with separate nodes for training and inference:

### Head Node (On one of your nodes):
```bash
ray start --head --dashboard-host=0.0.0.0
# Note the GCS address shown, e.g., ray://192.168.1.100:6379
```

### Worker Nodes (On other nodes):
```bash
ray start --address='ray://192.168.1.100:6379'  # Use the GCS address from head node
```

Verify cluster with:
```bash
ray status
```

---

## 2. **Configure Training Script (`run.sh`)**

Key vLLM server configurations in your `run.sh`:

```bash
# ================= Cluster Topology =================
export GPUS_PER_NODE=8                    # GPUs per node
NNODES=2                                   # Total number of nodes  
export RAY_NUM_NODES=$NNODES

# ================= vLLM Performance Settings =================
export VLLM_USE_V1=1
export VLLM_ATTENTION_BACKEND=FLASH_ATTN

# vLLM tensor parallel size (how many GPUs per inference instance)
infer_tp=1

# Launch training with async rollout mode
python3 -m verl.trainer.main_ppo \
    # ... other configs ...
    \
    # ============ CRITICAL: Async Rollout Configuration ============
    actor_rollout_ref.rollout.name=vllm \
    actor_rollout_ref.rollout.mode=async \                    # Enable async mode!
    actor_rollout_ref.rollout.tensor_model_parallel_size=$infer_tp \
    actor_rollout_ref.rollout.gpu_memory_utilization=0.75 \   # vLLM GPU memory usage
    actor_rollout_ref.rollout.max_num_seqs=1024 \            # Max concurrent sequences
    actor_rollout_ref.rollout.enable_prefix_caching=true \   # Enable KV cache
    \
    # ============ Agent Loop Configuration ============
    actor_rollout_ref.rollout.agent.agent_loop_config_path=$agent_loop_config_path \
    \
    # ============ Trainer Configuration ============
    trainer.n_gpus_per_node="$GPUS_PER_NODE" \
    trainer.nnodes="$NNODES"
```

---

## 3. **Resource Allocation Strategy**

VeRL automatically manages resource pools. You can configure separate resources for training vs inference:

### **Option A: Hybrid Mode (Default for AWorld)**
Training and inference share the same GPUs, switch context with weight synchronization:

```bash
actor_rollout_ref.rollout.mode=async  # Uses hybrid internally
```

### **Option B: Standalone Mode (True Train-Inference Decoupling)**
For the 14.6x speedup mentioned in the paper, use separate resource pools:

```python
# In your custom training script (similar to split_placement example)
from verl.trainer.ppo.ray_trainer import ResourcePoolManager, Role

# Define separate resource pools
resource_pool_spec = {
    'actor_pool': [8] * 1,      # 1 node with 8 GPUs for training
    'rollout_pool': [8] * 1,    # 1 node with 8 GPUs for inference
}

mapping = {
    Role.ActorRollout: 'actor_pool',   # Training on actor_pool
    Role.Rollout: 'rollout_pool',      # Inference on rollout_pool
}
```

---

## 4. **Agent Loop Configuration (`agent.yaml`)**

```yaml
- name: gaia_agent
  _target_: train.examples.train_gaia_with_aworld_verl.custom_agent_loop.GaiaAgentLoop
```

In your custom agent loop (`custom_agent_loop.py`):

```python
from aworld.agents.llm_agent import Agent
from aworld.config import AgentConfig
from train.adapter.verl.aworld_agent_loop import AworldAgentLoop
from train.adapter.common import get_agent_tool_env_and_servers

class GaiaAgentLoop(AworldAgentLoop):
    async def build_agents(self):
        gaia_env_config, gaia_env_servers = get_agent_tool_env_and_servers()
        
        return Agent(
            conf=AgentConfig(
                # Dynamically get vLLM server address from Ray actor
                llm_base_url=await self.get_llm_server_address(),
                llm_model_name=await self.get_llm_server_model_name(),
                llm_api_key="dummy",
            ),
            name="gaia_super_agent",
            system_prompt="<your_system_prompt>",
            mcp_config=gaia_env_config,
            mcp_servers=gaia_env_servers,
        )
```

---

## 5. **Submit Training Job**

### For Manual Ray Cluster:
```bash
ray job submit \
    --address="http://127.0.0.1:8265" \
    --runtime-env=verl/trainer/runtime_env.yaml \
    --no-wait \
    -- \
    bash /path/to/run.sh
```

### For Direct Execution:
```bash
# On the head node or with Ray already initialized
bash run.sh
```

---

## 6. **How It Works Under the Hood**

1. **VeRL creates vLLM servers** on designated Ray actors (inference nodes)
2. **AsyncLLMServerManager** manages multiple vLLM server instances with:
   - **Load balancing**: Distributes requests across servers
   - **Sticky sessions**: Routes multi-turn conversations to same server for prefix caching
3. **ZeroMQ communication** between training workers and vLLM inference engines
4. **Weight synchronization** via NCCL when needed (wake_up/sleep cycle)

---

## 7. **Key Configuration Parameters**

| Parameter | Purpose | Typical Value |
|-----------|---------|---------------|
| `rollout.mode` | Enable async mode | `async` |
| `rollout.name` | Inference engine | `vllm` or `sglang` |
| `rollout.tensor_model_parallel_size` | TP size for vLLM | `1`, `2`, `4`, or `8` |
| `rollout.gpu_memory_utilization` | vLLM GPU memory % | `0.75` |
| `rollout.max_num_seqs` | Concurrent sequences | `1024` |
| `trainer.nnodes` | Total nodes | `2` (1 train + 1 infer) |

---

## 8. **Monitoring**

Access Ray dashboard at `http://<head-node-ip>:8265` to:
- View resource allocation
- Monitor vLLM server status
- Check training/inference workload distribution

---

This setup achieves the **train-inference decoupled architecture** described in the AWorld paper, enabling parallel rollout generation on dedicated inference nodes while training runs on separate nodes, resulting in the 14.6x speedup!

---


*Exported from [Cursor View](https://github.com/saharmor/cursor-view)*