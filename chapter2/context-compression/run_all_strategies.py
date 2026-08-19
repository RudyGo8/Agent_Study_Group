#!/usr/bin/env python3
"""
顺序运行全部压缩策略并把结果写入日志的脚本
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from agent import ResearchAgent
from compression_strategies import CompressionStrategy, ContextCompressor
from config import Config
from colorama import init, Fore, Style

# 初始化 colorama
init(autoreset=True)


# CLI 简短别名 -> 压缩策略（顺序与书中实验 2-10 一致）
STRATEGY_CHOICES = {
    "no_compression": CompressionStrategy.NO_COMPRESSION,
    "individual": CompressionStrategy.NON_CONTEXT_AWARE_INDIVIDUAL,
    "combined": CompressionStrategy.NON_CONTEXT_AWARE_COMBINED,
    "context_aware": CompressionStrategy.CONTEXT_AWARE,
    "citations": CompressionStrategy.CONTEXT_AWARE_CITATIONS,
    "windowed": CompressionStrategy.WINDOWED_CONTEXT,
}

ALL_STRATEGIES = list(STRATEGY_CHOICES.values())

class StrategyRunner:
    """运行全部压缩策略并记录结果"""
    
    def __init__(self, log_dir: str = "logs"):
        """
        初始化策略运行器

        参数:
            log_dir: 日志文件的保存目录
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # 创建带时间戳的日志文件
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(log_dir, f"strategy_run_{timestamp}.log")
        self.json_file = os.path.join(log_dir, f"strategy_results_{timestamp}.json")
        
        # 配置日志
        self.setup_logging()

        # 结果存储
        self.results = []
        
    def setup_logging(self):
        """配置输出到文件和控制台的日志"""
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 文件处理器
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        
        # 控制台处理器 —— 过滤后输出更整洁
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        # 控制台用更简单的格式
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        
        # 配置日志器
        self.logger = logging.getLogger('StrategyRunner')
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
    def log_banner(self, message: str, char: str = "=", width: int = 70):
        """输出一条横幅式日志"""
        border = char * width
        self.logger.info(border)
        self.logger.info(message.center(width))
        self.logger.info(border)
        
    def run_strategy(self, strategy: CompressionStrategy) -> Dict[str, Any]:
        """
        运行单个压缩策略

        参数:
            strategy: 待测试的压缩策略

        返回:
            结果字典
        """
        self.log_banner(f"Testing: {strategy.value}", char="-")
        self.logger.info(f"Strategy: {strategy.value}")
        
        result = {
            'strategy': strategy.value,
            'start_time': datetime.now().isoformat(),
            'success': False,
            'error': None,
            'metrics': {}
        }
        
        try:
            # 用该策略创建 Agent
            self.logger.info("Creating agent...")
            agent = ResearchAgent(
                api_key=Config.MOONSHOT_API_KEY,
                compression_strategy=strategy,
                verbose=False,
                enable_streaming=True  # 开启流式以观察压缩过程
            )
            
            # 执行研究任务
            self.logger.info("Starting research task...")
            start_time = time.time()
            
            # 自定义流处理器，捕获流式输出并写入日志
            class StreamCapture:
                def __init__(self, logger, original_stdout):
                    self.logger = logger
                    self.original_stdout = original_stdout
                    self.buffer = []
                    self.current_line = []
                
                def write(self, text):
                    # 累积文本
                    self.current_line.append(text)
                    
                    # 出现换行符时，记录完整的行
                    if '\n' in text:
                        full_line = ''.join(self.current_line)
                        lines = full_line.split('\n')
                        
                        # 完整的行经 logger 记录（同时输出到控制台和文件）
                        for line in lines[:-1]:
                            if line.strip():
                                # 重要摘要用 INFO 级别，其余输出用 DEBUG
                                if any(keyword in line for keyword in ['📝', '🎯', '📚', '📄', 'Summarizing:', 'Creating']):
                                    self.logger.info(f"[COMPRESSION] {line}")
                                else:
                                    self.logger.debug(f"[AGENT] {line}")
                                self.buffer.append(line)
                        
                        # 残余的半行留给下次写入
                        self.current_line = [lines[-1]] if lines[-1] else []
                
                def flush(self):
                    # 冲刷剩余的半行
                    if self.current_line:
                        remaining = ''.join(self.current_line)
                        if remaining.strip():
                            self.logger.debug(f"[AGENT] {remaining}")
                            self.buffer.append(remaining)
                            self.current_line = []
                    
                def get_output(self):
                    # 确保剩余内容已全部冲刷
                    self.flush()
                    return '\n'.join(self.buffer)
            
            # 捕获流式输出
            original_stdout = sys.stdout
            stream_capture = StreamCapture(self.logger, original_stdout)
            
            try:
                sys.stdout = stream_capture
                research_result = agent.execute_research(max_iterations=Config.MAX_ITERATIONS)
            finally:
                sys.stdout = original_stdout
            
            execution_time = time.time() - start_time
            
            # 取出完整捕获结果用于保存
            output = stream_capture.get_output()
            
            # 把输出存入结果，便于后续分析
            result['agent_output'] = output
            
            # 处理结果
            trajectory = research_result.get('trajectory')
            
            if research_result.get('success'):
                result['success'] = True
                result['final_answer'] = research_result.get('final_answer', 'No answer found')
                self.logger.info("✅ Strategy completed successfully")
            else:
                result['error'] = research_result.get('error', 'Unknown error')
                self.logger.warning(f"⚠️ Strategy failed: {result['error']}")
            
            # 收集指标
            if trajectory:
                result['metrics'] = {
                    'execution_time': execution_time,
                    'tool_calls': len(trajectory.tool_calls),
                    'context_overflows': trajectory.context_overflows,
                    'total_tokens': trajectory.total_tokens_used,
                    'prompt_tokens': trajectory.prompt_tokens_used,
                    'completion_tokens': trajectory.completion_tokens_used
                }
                
                # 计算压缩统计
                total_original = 0
                total_compressed = 0
                
                for call in trajectory.tool_calls:
                    if call.compressed_result:
                        total_original += call.compressed_result.original_length
                        total_compressed += call.compressed_result.compressed_length
                
                if total_original > 0:
                    compression_ratio = total_compressed / total_original
                    result['metrics']['compression_ratio'] = compression_ratio
                    result['metrics']['total_original_size'] = total_original
                    result['metrics']['total_compressed_size'] = total_compressed
                    result['metrics']['space_saved'] = total_original - total_compressed
                
                # 记录指标
                self.logger.info(f"Execution time: {execution_time:.2f}s")
                self.logger.info(f"Tool calls: {result['metrics']['tool_calls']}")
                self.logger.info(f"Context overflows: {result['metrics']['context_overflows']}")
                self.logger.info(f"Total tokens: {result['metrics']['total_tokens']:,}")
                
                if 'compression_ratio' in result['metrics']:
                    self.logger.info(f"Compression ratio: {result['metrics']['compression_ratio']:.1%}")
                    self.logger.info(f"Space saved: {result['metrics']['space_saved']:,} chars")
                    
                # 记录每次工具调用的压缩细节
                self.logger.debug("\nCompression details by tool call:")
                for i, call in enumerate(trajectory.tool_calls, 1):
                    if call.compressed_result:
                        self.logger.debug(f"  Tool call {i}: {call.tool_name}")
                        self.logger.debug(f"    - Original: {call.compressed_result.original_length:,} chars")
                        self.logger.debug(f"    - Compressed: {call.compressed_result.compressed_length:,} chars")
                        self.logger.debug(f"    - Strategy: {call.compressed_result.strategy.value}")
            
        except Exception as e:
            result['error'] = str(e)
            self.logger.error(f"❌ Error running strategy: {e}", exc_info=True)
        
        result['end_time'] = datetime.now().isoformat()
        return result
    
    def run_all_strategies(self, strategies: Optional[List[CompressionStrategy]] = None):
        """运行给定的压缩策略（默认全部 6 种）"""
        if strategies is None:
            strategies = list(ALL_STRATEGIES)

        self.log_banner("COMPRESSION STRATEGIES TEST RUN", char="=")
        self.logger.info(f"Testing {len(strategies)} strategies")
        self.logger.info(f"Log file: {self.log_file}")
        self.logger.info(f"JSON results: {self.json_file}")
        
        # 逐个运行策略
        for i, strategy in enumerate(strategies, 1):
            self.logger.info(f"\n[{i}/{len(strategies)}] Running {strategy.value}")
            result = self.run_strategy(strategy)
            self.results.append(result)
            
            # 策略之间稍作延迟
            if i < len(strategies):
                time.sleep(2)
        
        # 生成小结
        self.generate_summary()
        
        # 保存结果为 JSON
        self.save_json_results()
        
        self.log_banner("TEST RUN COMPLETE", char="=")
        self.logger.info(f"Results saved to:")
        self.logger.info(f"  - Log: {self.log_file}")
        self.logger.info(f"  - JSON: {self.json_file}")
    
    def generate_summary(self):
        """生成并记录全部结果的小结"""
        self.log_banner("RESULTS SUMMARY", char="=")
        
        # 生成对比表
        self.logger.info("\nStrategy Comparison:")
        self.logger.info("-" * 100)
        self.logger.info(f"{'Strategy':<40} {'Success':<10} {'Time(s)':<10} {'Tokens':<12} {'Compression':<12} {'Overflows':<10}")
        self.logger.info("-" * 100)
        
        for result in self.results:
            strategy = result['strategy'][:38]  # 过长时截断
            success = "✅ Yes" if result['success'] else "❌ No"
            
            metrics = result.get('metrics', {})
            exec_time = f"{metrics.get('execution_time', 0):.2f}" if metrics else "N/A"
            tokens = f"{metrics.get('total_tokens', 0):,}" if metrics else "N/A"
            compression = f"{metrics.get('compression_ratio', 0):.1%}" if metrics.get('compression_ratio') else "N/A"
            overflows = str(metrics.get('context_overflows', 0)) if metrics else "N/A"
            
            self.logger.info(f"{strategy:<40} {success:<10} {exec_time:<10} {tokens:<12} {compression:<12} {overflows:<10}")
        
        self.logger.info("-" * 100)
        
        # 汇总统计
        successful = sum(1 for r in self.results if r['success'])
        failed = len(self.results) - successful
        
        self.logger.info(f"\nOverall Results:")
        self.logger.info(f"  - Successful: {successful}/{len(self.results)}")
        self.logger.info(f"  - Failed: {failed}/{len(self.results)}")
        
        # 找出表现最佳者
        if successful > 0:
            # 压缩率最优
            compressed_results = [r for r in self.results if r.get('metrics', {}).get('compression_ratio')]
            if compressed_results:
                best_compression = min(compressed_results, key=lambda r: r['metrics']['compression_ratio'])
                self.logger.info(f"  - Best compression: {best_compression['strategy']} ({best_compression['metrics']['compression_ratio']:.1%})")
            
            # 执行最快
            timed_results = [r for r in self.results if r.get('metrics', {}).get('execution_time')]
            if timed_results:
                fastest = min(timed_results, key=lambda r: r['metrics']['execution_time'])
                self.logger.info(f"  - Fastest: {fastest['strategy']} ({fastest['metrics']['execution_time']:.2f}s)")
            
            # token 用量
            token_results = [r for r in self.results if r.get('metrics', {}).get('total_tokens')]
            if token_results:
                most_tokens = max(token_results, key=lambda r: r['metrics']['total_tokens'])
                least_tokens = min(token_results, key=lambda r: r['metrics']['total_tokens'])
                self.logger.info(f"  - Most tokens: {most_tokens['strategy']} ({most_tokens['metrics']['total_tokens']:,})")
                self.logger.info(f"  - Least tokens: {least_tokens['strategy']} ({least_tokens['metrics']['total_tokens']:,})")
    
    def save_json_results(self):
        """把结果保存为 JSON 文件"""
        try:
            with open(self.json_file, 'w') as f:
                json.dump({
                    'run_date': datetime.now().isoformat(),
                    'config': {
                        'model': Config.MODEL_NAME,
                        'max_iterations': Config.MAX_ITERATIONS,
                        'context_window': Config.CONTEXT_WINDOW_SIZE,
                        'summary_max_tokens': Config.SUMMARY_MAX_TOKENS
                    },
                    'results': self.results
                }, f, indent=2)
            self.logger.info(f"JSON results saved to {self.json_file}")
        except Exception as e:
            self.logger.error(f"Failed to save JSON results: {e}")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="run_all_strategies.py",
        description="逐个运行压缩策略并将完整过程（含流式压缩摘要）写入日志。\n"
                    "与 experiment.py 相比，本脚本侧重“可复盘的详细日志”：每次运行都会生成 "
                    ".log 文本日志和 .json 结果文件，便于逐轮检查压缩效果。",
        epilog="示例：\n"
               "  python run_all_strategies.py                     # 运行全部 6 种策略\n"
               "  python run_all_strategies.py -s windowed         # 只跑自适应窗口化策略\n"
               "  python run_all_strategies.py --model kimi-k3 --log-dir logs/k2\n"
               "  python run_all_strategies.py --list-strategies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-s", "--strategy", nargs="+", choices=list(STRATEGY_CHOICES.keys()), metavar="NAME",
        help="要运行的压缩策略（可指定多个，默认运行全部 6 种）。可选值："
             + ", ".join(STRATEGY_CHOICES.keys()),
    )
    parser.add_argument(
        "-m", "--model", default=None,
        help=f"覆盖使用的模型名称（默认读取环境变量 MODEL_NAME，当前为 {Config.MODEL_NAME}）",
    )
    parser.add_argument(
        "--log-dir", default="logs", metavar="DIR",
        help="日志与 JSON 结果的输出目录（默认 logs/）",
    )
    parser.add_argument(
        "-n", "--max-iterations", type=int, default=None, metavar="N",
        help=f"每个策略允许的最大迭代（工具调用轮数），默认 {Config.MAX_ITERATIONS}",
    )
    parser.add_argument(
        "--list-strategies", action="store_true",
        help="列出所有可选的压缩策略名称后退出",
    )
    return parser


def main():
    """主入口"""
    parser = build_parser()
    args = parser.parse_args()

    if args.list_strategies:
        print("可选的压缩策略（--strategy 的取值）：")
        for alias, strat in STRATEGY_CHOICES.items():
            print(f"  {alias:<16} -> {strat.value}")
        return

    # 把命令行参数覆盖到共享的 Config
    if args.model:
        Config.MODEL_NAME = args.model
    if args.max_iterations is not None:
        Config.MAX_ITERATIONS = args.max_iterations

    strategies = ([STRATEGY_CHOICES[name] for name in args.strategy]
                  if args.strategy else list(ALL_STRATEGIES))

    print(f"\n{Fore.CYAN}{'='*70}")
    print(f"{Fore.CYAN}COMPRESSION STRATEGIES AUTOMATED TEST RUNNER")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}\n")

    # 校验配置
    if not Config.validate():
        print(f"{Fore.RED}Configuration validation failed!{Style.RESET_ALL}")
        print("\nPlease set up your .env file with:")
        print("  MOONSHOT_API_KEY=your_api_key_here")
        print("  SERPER_API_KEY=your_api_key_here (optional)")
        sys.exit(1)

    # 创建目录
    Config.create_directories()

    # 运行全部策略
    runner = StrategyRunner(log_dir=args.log_dir)

    try:
        print(f"{Fore.YELLOW}Starting test run...{Style.RESET_ALL}")
        print(f"Log file: {runner.log_file}\n")

        runner.run_all_strategies(strategies)
        
        print(f"\n{Fore.GREEN}✅ Test run complete!{Style.RESET_ALL}")
        print(f"\nResults saved to:")
        print(f"  📄 Log: {runner.log_file}")
        print(f"  📊 JSON: {runner.json_file}")
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Test run interrupted by user{Style.RESET_ALL}")
        runner.logger.warning("Test run interrupted by user")
    except Exception as e:
        print(f"\n{Fore.RED}Fatal error: {e}{Style.RESET_ALL}")
        runner.logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
