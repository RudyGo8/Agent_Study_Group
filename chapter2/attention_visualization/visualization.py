"""
注意力可视化工具
生成注意力模式的可视化呈现
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import seaborn as sns
from typing import List, Dict, Any, Optional, Tuple
import json
from pathlib import Path


def _configure_cjk_font():
    """
    尽力而为：挑选一个支持 CJK 的字体，让中文 token 标签（如第 2 章的
    '北京 的 天气 怎么样'示例）显示为字形而非"豆腐块"。未安装时静默跳过。
    """
    from matplotlib import font_manager
    candidates = [
        "Arial Unicode MS", "PingFang SC", "Hiragino Sans GB", "Heiti SC",
        "Songti SC", "STHeiti", "Noto Sans CJK SC", "Noto Sans CJK JP",
        "Microsoft YaHei", "WenQuanYi Zen Hei", "SimHei",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name] + list(
                plt.rcParams.get("font.sans-serif", [])
            )
            plt.rcParams["axes.unicode_minus"] = False
            return name
    return None


_configure_cjk_font()


def create_attention_heatmap(
    attention_weights: List[List[float]],
    input_tokens: List[str],
    output_tokens: List[str],
    context_boundary: int,
    title: str = "Attention Heatmap",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (14, 10),
    cmap: str = 'viridis'
) -> plt.Figure:
    """
    创建注意力权重的热力图可视化

    Args:
        attention_weights: 二维注意力权重列表 [output_len x total_len]
        input_tokens: 输入 token 列表
        output_tokens: 生成的 token 列表
        context_boundary: 输入结束、输出开始的位置
        title: 图表标题
        save_path: 可选的图片保存路径
        figsize: 图表尺寸
        cmap: 使用的色图

    Returns:
        matplotlib Figure 对象
    """
    # 处理变长注意力权重（三角模式）
    # 第 i 步有 context_boundary + i + 1 个注意力权重
    max_len = context_boundary + len(output_tokens)
    attention_matrix = np.zeros((len(attention_weights), max_len))
    
    for i, weights in enumerate(attention_weights):
        # 兼容列表和嵌套列表两种格式
        if weights and isinstance(weights[0], list):
            # 多头注意力时对各头取平均
            weights = np.array(weights).mean(axis=0).tolist()
        # 填入已有的权重
        attention_matrix[i, :len(weights)] = weights[:max_len]
    
    # 创建图和坐标轴
    fig, ax = plt.subplots(figsize=figsize)

    # 绘制热力图
    im = ax.imshow(attention_matrix, cmap=cmap, aspect='auto', vmin=0, vmax=1)

    # 设置刻度和标签
    all_tokens = input_tokens + output_tokens

    # X 轴（被关注对象）
    ax.set_xticks(np.arange(len(all_tokens)))
    ax.set_xticklabels(all_tokens, rotation=45, ha='right', fontsize=8)

    # Y 轴（生成的 token）
    ax.set_yticks(np.arange(len(output_tokens)))
    ax.set_yticklabels(output_tokens, fontsize=10)

    # 添加输入/输出分界线
    ax.axvline(x=context_boundary - 0.5, color='red', linewidth=2, linestyle='--', label='Input/Output Boundary')
    
    # 添加颜色条
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Attention Weight', rotation=270, labelpad=20)

    # 添加网格
    ax.set_xticks(np.arange(len(all_tokens) + 1) - 0.5, minor=True)
    ax.set_yticks(np.arange(len(output_tokens) + 1) - 0.5, minor=True)
    ax.grid(which='minor', color='gray', linestyle='-', linewidth=0.5, alpha=0.3)

    # 标签与标题
    ax.set_xlabel('Token Position (Input → Output)', fontsize=12)
    ax.set_ylabel('Generated Tokens', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')

    # 添加图例
    ax.legend(loc='upper right')

    # 调整布局
    plt.tight_layout()

    # 如提供路径则保存
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        
    return fig


def create_attention_flow_diagram(
    attention_steps: List[Dict],
    input_tokens: List[str],
    context_length: int,
    max_steps: int = 10,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (16, 10)
) -> plt.Figure:
    """
    创建展示注意力随生成步骤演变的流程图

    Args:
        attention_steps: 注意力步骤字典列表
        input_tokens: 输入 token 列表
        context_length: 输入上下文长度
        max_steps: 可视化的最大步数
        save_path: 可选的图片保存路径
        figsize: 图表尺寸

    Returns:
        matplotlib Figure 对象
    """
    # 必要时限制步数
    steps_to_show = min(len(attention_steps), max_steps)

    # 创建子图
    fig, axes = plt.subplots(1, steps_to_show, figsize=figsize, sharey=True)
    
    if steps_to_show == 1:
        axes = [axes]
    
    for idx, step in enumerate(attention_steps[:steps_to_show]):
        ax = axes[idx]
        
        # 获取该步骤的注意力权重
        attention = np.array(step['attention_weights'])

        # 兼容一维和二维注意力
        if attention.ndim == 2:
            # 必要时对各头取平均
            attention = attention.mean(axis=0)

        # 确保注意力归一化
        if attention.sum() > 0:
            attention = attention / attention.sum()

        # 绘制条形图
        positions = np.arange(len(attention))
        colors = ['blue' if i < context_length else 'red' for i in positions]
        
        bars = ax.bar(positions, attention, color=colors, alpha=0.7)
        
        # 高亮注意力最高的位置
        top_k = min(3, len(attention))
        top_indices = np.argsort(attention)[-top_k:]
        for i in top_indices:
            bars[i].set_alpha(1.0)
            bars[i].set_edgecolor('black')
            bars[i].set_linewidth(2)
        
        # 标签
        ax.set_title(f"Step {step['step']}\nToken: '{step['token']}'", fontsize=10)
        ax.set_xlabel('Position', fontsize=8)
        if idx == 0:
            ax.set_ylabel('Attention Weight', fontsize=10)
        
        # 添加上下文分界线
        ax.axvline(x=context_length - 0.5, color='green', linestyle='--', alpha=0.5)

        # 限制 y 轴范围以便观察
        ax.set_ylim(0, min(1.0, attention.max() * 1.2))
        
    # 总标题
    fig.suptitle('Attention Flow During Generation', fontsize=14, fontweight='bold')

    # 添加图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='blue', alpha=0.7, label='Input Context'),
        Patch(facecolor='red', alpha=0.7, label='Generated'),
        Patch(facecolor='green', alpha=0.5, label='Context Boundary')
    ]
    fig.legend(handles=legend_elements, loc='upper right')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        
    return fig


def create_token_attention_summary(
    result: Dict,
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (14, 8)
) -> plt.Figure:
    """
    创建汇总可视化，展示 token 及其注意力模式

    Args:
        result: 生成结果字典
        save_path: 可选的图片保存路径
        figsize: 图表尺寸

    Returns:
        matplotlib Figure 对象
    """
    fig = plt.figure(figsize=figsize)

    # 创建子图网格
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 2, 2], width_ratios=[1, 1])

    # 1. token 序列展示
    ax_tokens = fig.add_subplot(gs[0, :])
    ax_tokens.axis('off')

    # 展示输入 token
    input_text = "Input: " + "".join(result['input_tokens'][:50])  # 限制显示数量
    ax_tokens.text(0.05, 0.7, input_text, fontsize=10, color='blue',
                   wrap=True, transform=ax_tokens.transAxes)

    # 展示输出 token
    output_text = "Output: " + "".join(result['output_tokens'][:50])
    ax_tokens.text(0.05, 0.3, output_text, fontsize=10, color='red',
                   wrap=True, transform=ax_tokens.transAxes)
    
    # 2. 注意力统计
    ax_stats = fig.add_subplot(gs[1, 0])

    if result['attention_steps']:
        # 计算统计量
        avg_attentions = []
        max_attentions = []
        
        for step in result['attention_steps']:
            weights = np.array(step['attention_weights'])
            if weights.ndim == 2:
                weights = weights.mean(axis=0)
            avg_attentions.append(weights.mean())
            max_attentions.append(weights.max())
        
        steps = np.arange(len(avg_attentions))
        
        ax_stats.plot(steps, avg_attentions, 'b-', label='Average', linewidth=2)
        ax_stats.plot(steps, max_attentions, 'r-', label='Maximum', linewidth=2)
        ax_stats.fill_between(steps, avg_attentions, alpha=0.3)
        
        ax_stats.set_xlabel('Generation Step')
        ax_stats.set_ylabel('Attention Weight')
        ax_stats.set_title('Attention Statistics Over Time')
        ax_stats.legend()
        ax_stats.grid(True, alpha=0.3)
    
    # 3. 注意力分布直方图
    ax_hist = fig.add_subplot(gs[1, 1])
    
    if result['attention_steps']:
        all_weights = []
        for step in result['attention_steps']:
            weights = np.array(step['attention_weights'])
            if weights.ndim == 2:
                weights = weights.mean(axis=0)
            all_weights.extend(weights.tolist())
        
        ax_hist.hist(all_weights, bins=50, alpha=0.7, color='green', edgecolor='black')
        ax_hist.set_xlabel('Attention Weight')
        ax_hist.set_ylabel('Frequency')
        ax_hist.set_title('Attention Weight Distribution')
        ax_hist.axvline(np.mean(all_weights), color='red', linestyle='--', 
                       label=f'Mean: {np.mean(all_weights):.3f}')
        ax_hist.legend()
    
    # 4. 被关注最多的位置
    ax_top = fig.add_subplot(gs[2, :])

    if result['attention_steps']:
        # 聚合所有步骤的注意力
        context_len = result['context_length']
        total_len = context_len + len(result['output_tokens'])
        aggregated_attention = np.zeros(total_len)
        
        for step in result['attention_steps']:
            weights = np.array(step['attention_weights'])
            if weights.ndim == 2:
                weights = weights.mean(axis=0)
            aggregated_attention[:len(weights)] += weights
        
        # 归一化
        aggregated_attention /= len(result['attention_steps'])

        # 绘制条形图
        positions = np.arange(len(aggregated_attention))
        colors = ['blue' if i < context_len else 'red' for i in positions]
        
        ax_top.bar(positions, aggregated_attention, color=colors, alpha=0.7)
        ax_top.axvline(x=context_len - 0.5, color='green', linestyle='--', 
                      label='Context Boundary')
        
        # 高亮 top 位置
        top_k = min(5, len(aggregated_attention))
        top_indices = np.argsort(aggregated_attention)[-top_k:]
        for idx in top_indices:
            ax_top.annotate(f'{idx}', xy=(idx, aggregated_attention[idx]),
                           xytext=(idx, aggregated_attention[idx] + 0.01),
                           ha='center', fontsize=8)
        
        ax_top.set_xlabel('Token Position')
        ax_top.set_ylabel('Average Attention')
        ax_top.set_title('Aggregated Attention Across All Generation Steps')
        ax_top.legend()
    
    plt.suptitle('Attention Analysis Summary', fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        
    return fig


def visualize_results(
    results_path: str,
    output_dir: str = "visualizations",
    formats: List[str] = ['heatmap', 'flow', 'summary']
):
    """
    根据已保存的结果生成可视化

    Args:
        results_path: JSON 结果文件路径
        output_dir: 可视化输出目录
        formats: 要生成哪些可视化格式
    """
    # 加载结果
    with open(results_path, 'r') as f:
        results = json.load(f)

    # 创建输出目录
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    # 逐个处理结果
    for idx, result in enumerate(results):
        print(f"Generating visualizations for result {idx + 1}...")

        # 提取数据
        input_tokens = result['input_tokens']
        output_tokens = result['output_tokens']
        attention_steps = result['attention_steps']
        context_length = result['context_length']
        
        # 为热力图构建注意力矩阵
        if 'heatmap' in formats and attention_steps:
            attention_matrix = []
            for step in attention_steps:
                weights = step['attention_weights']
                if isinstance(weights[0], list):  # 2D
                    weights = np.array(weights).mean(axis=0).tolist()
                attention_matrix.append(weights)
            
            fig = create_attention_heatmap(
                attention_matrix,
                input_tokens,
                output_tokens,
                context_length,
                title=f"Attention Heatmap - Example {idx + 1}",
                save_path=output_path / f"heatmap_{idx + 1}.png"
            )
            plt.close(fig)
        
        # 创建流程图
        if 'flow' in formats and attention_steps:
            fig = create_attention_flow_diagram(
                attention_steps,
                input_tokens,
                context_length,
                save_path=output_path / f"flow_{idx + 1}.png"
            )
            plt.close(fig)
        
        # 创建汇总图
        if 'summary' in formats:
            fig = create_token_attention_summary(
                result,
                save_path=output_path / f"summary_{idx + 1}.png"
            )
            plt.close(fig)
    
    print(f"Visualizations saved to {output_path}")


def clean_token_labels(tokens: List[str], max_len: int = 14) -> List[str]:
    """
    把分词器输出的原始 token 整理成可读的坐标轴标签。

    将空白替换为可见符号，并截断过长的特殊 token，
    保证热力图坐标轴清晰可读。
    """
    cleaned = []
    for tok in tokens:
        label = tok.replace("\n", "\\n").replace("\t", "\\t")
        # Qwen 的字节级空格标记和普通空格 -> 可见的间隔符号
        label = label.replace("Ġ", " ").replace("▁", " ")
        if label.strip() == "":
            label = "␣"
        if len(label) > max_len:
            label = label[:max_len - 1] + "…"
        cleaned.append(label)
    return cleaned


def attention_sink_stats(attention_matrix: np.ndarray, sink_index: int = 0) -> Dict[str, float]:
    """
    计算有多少注意力落在单个"sink"列上。

    对所有能看到 sink 列的查询行取平均，得到分配给 ``sink_index`` 的
    注意力权重。由此量化第 2 章描述的"注意力汇聚（attention sink）"
    现象，不虚构任何数字——直接从模型自身权重测得。

    返回包含 sink 占比均值与最大值（0..1）的字典。
    """
    matrix = np.asarray(attention_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        return {"mean_sink_share": 0.0, "max_sink_share": 0.0}

    shares = []
    for row_idx in range(matrix.shape[0]):
        # 因果关系下，一行只关注 <= row_idx 的位置。
        if row_idx < sink_index:
            continue
        row = matrix[row_idx, : row_idx + 1]
        total = row.sum()
        if total > 0:
            shares.append(float(matrix[row_idx, sink_index] / total))

    if not shares:
        return {"mean_sink_share": 0.0, "max_sink_share": 0.0}
    return {
        "mean_sink_share": float(np.mean(shares)),
        "max_sink_share": float(np.max(shares)),
    }


def create_layer_attention_heatmap(
    attention_matrix: np.ndarray,
    tokens: List[str],
    title: str = "Attention Heatmap",
    save_path: Optional[str] = None,
    figsize: Tuple[int, int] = (12, 10),
    cmap: str = "viridis",
    context_boundary: Optional[int] = None,
    annotate_sink: bool = True,
) -> plt.Figure:
    """
    绘制某一层/某个头的完整 [seq x seq] 自注意力矩阵。

    行是 Query 位置（发起关注的 token），列是 Key 位置（被关注的
    token）。由于生成是因果的，矩阵呈下三角——每个 token 只能看到
    自己和之前的 token，形成第 2 章讨论的三角模式。

    Args:
        attention_matrix: 二维数组 [seq, seq]。上三角已被掩蔽。
        tokens: 两个坐标轴共用的 token 字符串（长度为 seq）。
        title: 图表标题。
        save_path: 可选的 PNG 保存路径。
        figsize: 图表尺寸。
        cmap: Matplotlib 色图。
        context_boundary: 若给定，在提示结束、生成 token 开始处画线。
        annotate_sink: 若为 True，标注实测的注意力汇聚占比。

    Returns:
        matplotlib Figure 对象。
    """
    matrix = np.asarray(attention_matrix, dtype=float)
    seq_len = matrix.shape[0]

    # 把（结构上为零的）上三角掩蔽成空白而非深色，
    # 让因果三角一目了然。
    masked = np.ma.array(matrix, mask=np.triu(np.ones_like(matrix, dtype=bool), k=1))

    fig, ax = plt.subplots(figsize=figsize)
    cmap_obj = plt.get_cmap(cmap).copy()
    cmap_obj.set_bad(color="#f0f0f0")
    im = ax.imshow(masked, cmap=cmap_obj, aspect="auto")

    labels = clean_token_labels(tokens)
    # 长序列时避免密密麻麻无法阅读的标签。
    if seq_len <= 80:
        ticks = np.arange(seq_len)
    else:
        step = int(np.ceil(seq_len / 80))
        ticks = np.arange(0, seq_len, step)
    tick_labels = [labels[i] for i in ticks]

    ax.set_xticks(ticks)
    ax.set_xticklabels(tick_labels, rotation=90, fontsize=6)
    ax.set_yticks(ticks)
    ax.set_yticklabels(tick_labels, fontsize=6)

    if context_boundary is not None and 0 < context_boundary < seq_len:
        ax.axvline(x=context_boundary - 0.5, color="red", linewidth=1.2,
                   linestyle="--", label="Prompt / Generated boundary")
        ax.axhline(y=context_boundary - 0.5, color="red", linewidth=1.2,
                   linestyle="--")
        ax.legend(loc="lower left", fontsize=8)

    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Attention Weight", rotation=270, labelpad=15)

    ax.set_xlabel("Key position (attended to)", fontsize=11)
    ax.set_ylabel("Query position (attending from)", fontsize=11)

    if annotate_sink:
        stats = attention_sink_stats(matrix, sink_index=0)
        title = (f"{title}\nAttention sink (token 0): "
                 f"mean {stats['mean_sink_share'] * 100:.1f}% / "
                 f"max {stats['max_sink_share'] * 100:.1f}% of each row")

    ax.set_title(title, fontsize=12, fontweight="bold")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


def create_attention_comparison(
    matrices: List[np.ndarray],
    tokens_list: List[List[str]],
    titles: List[str],
    save_path: Optional[str] = None,
    figsize: Optional[Tuple[int, int]] = None,
    cmap: str = "viridis",
    suptitle: str = "Attention Pattern Comparison",
) -> plt.Figure:
    """
    并排绘制多个 [seq x seq] 注意力矩阵以便对比。

    用于对照不同的注意力模式——例如两个不同的层、两个提示、或有工具
    vs 无工具——对应第 2 章的讨论。
    """
    n = len(matrices)
    if figsize is None:
        figsize = (7 * n, 6)
    fig, axes = plt.subplots(1, n, figsize=figsize)
    if n == 1:
        axes = [axes]

    cmap_obj = plt.get_cmap(cmap).copy()
    cmap_obj.set_bad(color="#f0f0f0")

    for ax, matrix, tokens, title in zip(axes, matrices, tokens_list, titles):
        matrix = np.asarray(matrix, dtype=float)
        masked = np.ma.array(matrix, mask=np.triu(np.ones_like(matrix, dtype=bool), k=1))
        im = ax.imshow(masked, cmap=cmap_obj, aspect="auto")

        seq_len = matrix.shape[0]
        labels = clean_token_labels(tokens)
        if seq_len <= 40:
            ticks = np.arange(seq_len)
        else:
            step = int(np.ceil(seq_len / 40))
            ticks = np.arange(0, seq_len, step)
        ax.set_xticks(ticks)
        ax.set_xticklabels([labels[i] for i in ticks], rotation=90, fontsize=5)
        ax.set_yticks(ticks)
        ax.set_yticklabels([labels[i] for i in ticks], fontsize=5)

        stats = attention_sink_stats(matrix, sink_index=0)
        ax.set_title(f"{title}\nsink mean {stats['mean_sink_share'] * 100:.1f}%",
                     fontsize=10, fontweight="bold")
        ax.set_xlabel("Key position", fontsize=9)
        ax.set_ylabel("Query position", fontsize=9)
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.suptitle(suptitle, fontsize=13, fontweight="bold")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")

    return fig


if __name__ == "__main__":
    # 用法示例
    import sys
    
    if len(sys.argv) > 1:
        results_file = sys.argv[1]
    else:
        results_file = "attention_results.json"
    
    if Path(results_file).exists():
        visualize_results(results_file)
    else:
        print(f"Results file {results_file} not found. Run agent.py first.")
