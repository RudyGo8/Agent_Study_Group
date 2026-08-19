"""
带工具调用支持的 Qwen3 vLLM 服务端启动器
"""

import os
import sys
import subprocess
import time
import requests
from pathlib import Path
from config import VLLM_SERVER_CONFIG, VLLM_HOST, VLLM_PORT
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VLLMServer:
    """vLLM 服务端进程管理器"""
    
    def __init__(self, config: dict = None):
        """按配置初始化服务端管理器"""
        self.config = config or VLLM_SERVER_CONFIG
        self.process = None
        self.server_url = f"http://{self.config['host']}:{self.config['port']}"
    
    def _build_command(self) -> list:
        """构建带参数的 vLLM 服务端启动命令"""
        cmd = [
            sys.executable, "-m", "vllm.entrypoints.openai.api_server",
            "--model", self.config["model"],
            "--port", str(self.config["port"]),
            "--host", self.config["host"],
        ]
        
        # 追加工具相关参数
        if self.config.get("enable_auto_tool_choice"):
            cmd.append("--enable-auto-tool-choice")
        
        if self.config.get("tool_call_parser"):
            cmd.extend(["--tool-call-parser", self.config["tool_call_parser"]])
        
        if self.config.get("chat_template"):
            cmd.extend(["--chat-template", self.config["chat_template"]])
        
        # 追加性能相关参数
        if self.config.get("max_model_len"):
            cmd.extend(["--max-model-len", str(self.config["max_model_len"])])
        
        if self.config.get("gpu_memory_utilization"):
            cmd.extend(["--gpu-memory-utilization", str(self.config["gpu_memory_utilization"])])
        
        if self.config.get("dtype"):
            cmd.extend(["--dtype", self.config["dtype"]])
        
        if self.config.get("enforce_eager"):
            cmd.append("--enforce-eager")
        
        # 多 GPU 时追加 tensor parallel size
        if self.config.get("tensor_parallel_size"):
            cmd.extend(["--tensor-parallel-size", str(self.config["tensor_parallel_size"])])
        
        return cmd
    
    def start(self, wait_for_ready: bool = True, timeout: int = 120):
        """
        启动 vLLM 服务端

        Args:
            wait_for_ready: 是否等待服务端就绪
            timeout: 等待服务端启动的最长时间
        """
        if self.is_running():
            logger.info("vLLM server is already running")
            return
        
        # 创建日志目录
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # 构建命令
        cmd = self._build_command()
        logger.info(f"Starting vLLM server with command: {' '.join(cmd)}")
        
        # 启动服务端进程
        log_file = log_dir / "vllm_server.log"
        with open(log_file, "w") as f:
            self.process = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=os.environ.copy()
            )
        
        logger.info(f"vLLM server process started with PID: {self.process.pid}")
        logger.info(f"Server logs are being written to: {log_file}")
        
        if wait_for_ready:
            self._wait_for_ready(timeout)
    
    def _wait_for_ready(self, timeout: int = 120):
        """等待服务端就绪"""
        start_time = time.time()
        health_url = f"{self.server_url}/health"
        
        logger.info(f"Waiting for vLLM server to be ready at {health_url}...")
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(health_url, timeout=1)
                if response.status_code == 200:
                    logger.info("vLLM server is ready!")
                    
                    # 验证模型可用性
                    models_url = f"{self.server_url}/v1/models"
                    models_response = requests.get(models_url)
                    if models_response.status_code == 200:
                        models = models_response.json()
                        logger.info(f"Available models: {models}")
                    return
            except requests.exceptions.RequestException:
                pass
            
            # 检查进程是否仍在运行
            if self.process and self.process.poll() is not None:
                raise RuntimeError(f"vLLM server process died with code: {self.process.returncode}")
            
            time.sleep(2)
        
        raise TimeoutError(f"vLLM server did not start within {timeout} seconds")
    
    def stop(self):
        """停止 vLLM 服务端"""
        if self.process:
            logger.info("Stopping vLLM server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Server did not stop gracefully, forcing kill...")
                self.process.kill()
                self.process.wait()
            
            self.process = None
            logger.info("vLLM server stopped")
    
    def is_running(self) -> bool:
        """检查服务端是否在运行"""
        if not self.process:
            return False
        
        # 检查进程是否存活
        if self.process.poll() is not None:
            return False
        
        # 尝试访问健康检查端点
        try:
            response = requests.get(f"{self.server_url}/health", timeout=1)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def restart(self):
        """重启服务端"""
        logger.info("Restarting vLLM server...")
        self.stop()
        time.sleep(2)
        self.start()


def download_model_from_modelscope():
    """
    从 ModelScope 下载 Qwen3-0.6B 模型
    可选步骤——vLLM 也能自动从 HuggingFace 下载
    """
    try:
        from modelscope import snapshot_download
        
        model_dir = snapshot_download(
            'Qwen/Qwen3-0.6B',
            cache_dir='./models'
        )
        logger.info(f"Model downloaded to: {model_dir}")
        return model_dir
    except ImportError:
        logger.warning("ModelScope not installed. Install with: pip install modelscope")
        logger.info("vLLM will download from HuggingFace instead")
        return None


def main():
    """启动 vLLM 服务端的主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Start vLLM server with Qwen3 model")
    parser.add_argument("--download", action="store_true", 
                       help="Download model from ModelScope first")
    parser.add_argument("--model", type=str, default=None,
                       help="Model name or path (overrides config)")
    parser.add_argument("--port", type=int, default=None,
                       help="Server port (overrides config)")
    parser.add_argument("--host", type=str, default=None,
                       help="Server host (overrides config)")
    
    args = parser.parse_args()
    
    # 按需先下载模型
    if args.download:
        model_path = download_model_from_modelscope()
        if model_path:
            VLLM_SERVER_CONFIG["model"] = model_path
    
    # 用命令行参数覆盖配置
    if args.model:
        VLLM_SERVER_CONFIG["model"] = args.model
    if args.port:
        VLLM_SERVER_CONFIG["port"] = args.port
    if args.host:
        VLLM_SERVER_CONFIG["host"] = args.host
    
    # 创建并启动服务端
    server = VLLMServer(VLLM_SERVER_CONFIG)
    
    try:
        server.start(wait_for_ready=True)
        logger.info(f"vLLM server is running at {server.server_url}")
        logger.info("Press Ctrl+C to stop the server")
        
        # 维持服务端运行
        while True:
            time.sleep(1)
            if not server.is_running():
                logger.error("Server stopped unexpectedly!")
                break
                
    except KeyboardInterrupt:
        logger.info("\nShutting down...")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
