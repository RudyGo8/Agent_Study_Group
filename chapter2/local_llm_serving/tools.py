"""
用于演示 vLLM 工具调用功能的示例工具
"""
import json
import math
import random
import io
import contextlib
from typing import Dict, Any, List
from datetime import datetime
import requests
from io import BytesIO
import PyPDF2


class ToolRegistry:
    """管理可用工具的注册表"""
    
    def __init__(self):
        self.tools = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """注册默认工具"""
        self.register_tool(
            name="get_current_temperature",
            function=self.get_current_temperature,
            description="Get the current temperature for a specific location",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and country, e.g., 'Paris, France'"
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "The temperature unit to use (by default, celsius)"
                    }
                },
                "required": ["location", "unit"]
            }
        )
        
        self.register_tool(
            name="get_current_time",
            function=self.get_current_time,
            description="Get the current date and time in a specific timezone",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone name (e.g., 'America/New_York', 'Europe/London', 'Asia/Tokyo'). Use standard IANA timezone names.",
                        "default": "UTC"
                    }
                },
                "required": []
            }
        )
        
        self.register_tool(
            name="convert_currency",
            function=self.convert_currency,
            description="Convert an amount from one currency to another. You MUST use this tool to convert currencies in order to get the latest exchange rate.",
            parameters={
                "type": "object",
                "properties": {
                    "amount": {
                        "type": "number",
                        "description": "Amount to convert"
                    },
                    "from_currency": {
                        "type": "string",
                        "description": "Source currency code (e.g., 'USD', 'EUR')"
                    },
                    "to_currency": {
                        "type": "string",
                        "description": "Target currency code (e.g., 'USD', 'EUR')"
                    }
                },
                "required": ["amount", "from_currency", "to_currency"]
            }
        )

        self.register_tool(
            name="code_interpreter",
            function=self.code_interpreter,
            description="Execute Python code for calculations and data processing. You MUST use this tool to perform any complex calculations or data processing.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute. Use Python operators: ** for exponentiation (2 ** 10), not ^ — in Python ^ is bitwise XOR."
                    }
                },
                "required": ["code"]
            }
        )
    
    def register_tool(self, name: str, function: callable, description: str, parameters: Dict):
        """注册新工具"""
        self.tools[name] = {
            "function": function,
            "description": description,
            "parameters": parameters
        }
    
    def get_tool_schemas(self) -> List[Dict]:
        """获取 OpenAI 兼容格式的工具 schema"""
        schemas = []
        for name, tool in self.tools.items():
            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            })
        return schemas
    
    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """按名称和参数执行工具"""
        if name not in self.tools:
            return json.dumps({"error": f"Tool '{name}' not found"})
        
        try:
            result = self.tools[name]["function"](**arguments)
            return json.dumps(result) if isinstance(result, (dict, list)) else str(result)
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    # 工具实现
    @staticmethod
    def get_current_temperature(location: str, unit: str = "celsius") -> Dict:
        """
        使用 Open-Meteo 免费天气 API 获取当前气温
        无需 API key - https://open-meteo.com/
        """
        try:
            # 先做地理编码，把地点转成经纬度
            geocoding_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_params = {
                "name": location,
                "count": 1,
                "language": "en",
                "format": "json"
            }
            
            geo_response = requests.get(geocoding_url, params=geo_params, timeout=5)
            geo_data = geo_response.json()
            
            if not geo_data.get("results"):
                return {
                    "location": location,
                    "error": f"Location '{location}' not found",
                    "timestamp": datetime.now().isoformat()
                }
            
            # 从第一条结果取坐标
            result = geo_data["results"][0]
            latitude = result["latitude"]
            longitude = result["longitude"]
            location_name = f"{result.get('name', location)}, {result.get('country', '')}"
            
            # 从 Open-Meteo 获取当前天气
            weather_url = "https://api.open-meteo.com/v1/forecast"
            
            # 确定温度单位
            temp_unit = "fahrenheit" if unit.lower() == "fahrenheit" else "celsius"
            
            weather_params = {
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                "temperature_unit": temp_unit,
                "timezone": "auto"
            }
            
            weather_response = requests.get(weather_url, params=weather_params, timeout=5)
            weather_data = weather_response.json()
            
            if "current" not in weather_data:
                return {
                    "location": location_name,
                    "error": "Weather data not available",
                    "timestamp": datetime.now().isoformat()
                }
            
            current = weather_data["current"]
            
            # 把天气代码映射为天气状况
            weather_codes = {
                0: "clear sky",
                1: "mainly clear", 2: "partly cloudy", 3: "overcast",
                45: "foggy", 48: "foggy",
                51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
                61: "light rain", 63: "moderate rain", 65: "heavy rain",
                71: "light snow", 73: "moderate snow", 75: "heavy snow",
                77: "snow grains",
                80: "light rain showers", 81: "moderate rain showers", 82: "heavy rain showers",
                85: "light snow showers", 86: "heavy snow showers",
                95: "thunderstorm", 96: "thunderstorm with light hail", 99: "thunderstorm with heavy hail"
            }
            
            weather_code = current.get("weather_code", 0)
            conditions = weather_codes.get(weather_code, "unknown")
            
            unit_symbol = "°F" if unit.lower() == "fahrenheit" else "°C"
            
            return {
                "location": location_name,
                "temperature": round(current["temperature_2m"], 1),
                "unit": unit_symbol,
                "conditions": conditions,
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed": round(current.get("wind_speed_10m", 0), 1),
                "wind_unit": "km/h",
                "coordinates": {"latitude": latitude, "longitude": longitude},
                "timestamp": current.get("time", datetime.now().isoformat()),
                "source": "Open-Meteo"
            }
            
        except requests.RequestException as e:
            # API 失败时回退为模拟数据
            import logging
            logging.warning(f"Open-Meteo API error: {e}. Using simulated data.")
            
            # 模拟数据兜底
            base_temp = 20 + random.uniform(-10, 10)
            
            if unit == "fahrenheit":
                temp = base_temp * 9/5 + 32
                unit_symbol = "°F"
            else:
                temp = base_temp
                unit_symbol = "°C"
            
            return {
                "location": location,
                "temperature": round(temp, 1),
                "unit": unit_symbol,
                "conditions": random.choice(["sunny", "cloudy", "partly cloudy", "rainy"]),
                "timestamp": datetime.now().isoformat(),
                "note": "Simulated data (API unavailable)"
            }
        except Exception as e:
            return {
                "location": location,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    @staticmethod
    def get_current_time(timezone: str = "UTC") -> Dict:
        """
        使用 zoneinfo（Python 3.9+）获取指定时区的当前日期时间
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo
        
        # 常见时区缩写到 IANA 时区名的映射
        timezone_aliases = {
            "EST": "America/New_York",
            "EDT": "America/New_York",
            "PST": "America/Los_Angeles",
            "PDT": "America/Los_Angeles",
            "CST": "America/Chicago",
            "CDT": "America/Chicago",
            "MST": "America/Denver",
            "MDT": "America/Denver",
            "GMT": "Europe/London",
            "BST": "Europe/London",
            "CET": "Europe/Paris",
            "CEST": "Europe/Paris",
            "JST": "Asia/Tokyo",
            "IST": "Asia/Kolkata",
            "AEST": "Australia/Sydney",
            "AEDT": "Australia/Sydney",
            "SGT": "Asia/Singapore",
            "HKT": "Asia/Hong_Kong",
            "UTC+1": "Etc/GMT-1",  # 注意：Etc/GMT 中的正负号是反的
            "UTC-1": "Etc/GMT+1",
            "UTC+8": "Etc/GMT-8",
            "UTC-8": "Etc/GMT+8"
        }
        
        # 如有必要，把缩写转换为 IANA 名称
        tz_name = timezone_aliases.get(timezone.upper(), timezone)
        
        try:
            tz = ZoneInfo(tz_name)
            current_time = datetime.now(tz)
            
            return {
                "timezone": tz_name,
                "datetime": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                "date": current_time.strftime("%Y-%m-%d"),
                "time": current_time.strftime("%H:%M:%S"),
                "day_of_week": current_time.strftime("%A"),
                "utc_offset": current_time.strftime("%z"),
                "timestamp": current_time.isoformat()
            }
        except Exception as e:
            # 时区找不到时回退到 UTC
            try:
                tz_utc = ZoneInfo("UTC")
                current_time = datetime.now(tz_utc)
                return {
                    "timezone": "UTC",
                    "datetime": current_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "date": current_time.strftime("%Y-%m-%d"),
                    "time": current_time.strftime("%H:%M:%S"),
                    "day_of_week": current_time.strftime("%A"),
                    "utc_offset": "+0000",
                    "timestamp": current_time.isoformat(),
                    "note": f"Invalid timezone '{timezone}', using UTC as fallback"
                }
            except Exception as fallback_error:
                return {
                    "error": str(e),
                    "fallback_error": str(fallback_error),
                    "timezone": timezone,
                    "timestamp": datetime.utcnow().isoformat()
                }
    
    @staticmethod
    def convert_currency(amount: float, from_currency: str, to_currency: str) -> Dict:
        """
        按汇率换算货币（模拟汇率）
        """
        # 归一化货币代码
        from_currency = from_currency.upper().replace("S$", "SGD").replace("$", "USD")
        to_currency = to_currency.upper().replace("S$", "SGD").replace("$", "USD")
        
        # 模拟汇率
        exchange_rates = {
            "USD": 1.0,
            "EUR": 0.92,
            "GBP": 0.79,
            "JPY": 149.50,
            "CNY": 7.24,
            "CAD": 1.36,
            "AUD": 1.53,
            "CHF": 0.88,
            "INR": 83.12,
            "SGD": 1.34,
            "KRW": 1330.50,
            "MXN": 17.10
        }
        
        if from_currency not in exchange_rates or to_currency not in exchange_rates:
            return {"error": f"Unsupported currency: {from_currency} or {to_currency}"}
        
        # 先换成 USD，再换算成目标货币
        usd_amount = amount / exchange_rates[from_currency]
        converted_amount = usd_amount * exchange_rates[to_currency]
        
        return {
            "original_amount": amount,
            "from_currency": from_currency,
            "to_currency": to_currency,
            "converted_amount": round(converted_amount, 2),
            "exchange_rate": round(exchange_rates[to_currency] / exchange_rates[from_currency], 4),
            "timestamp": datetime.now().isoformat()
        }
    
    @staticmethod
    def parse_pdf(url: str) -> Dict:
        """
        解析 URL 或本地文件中的 PDF 文档
        """
        try:
            # 判断是否为本地文件
            if url.startswith('file://') or url.startswith('/') or url.startswith('./'):
                # 本地文件
                file_path = url.replace('file://', '')
                with open(file_path, 'rb') as f:
                    pdf_content = f.read()
            else:
                # 远程 URL
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                pdf_content = response.content
            
            # 解析 PDF
            pdf_file = BytesIO(pdf_content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            text_content = []
            for page_num, page in enumerate(pdf_reader.pages, 1):
                text = page.extract_text()
                text_content.append({
                    "page": page_num,
                    "text": text[:1000]  # 限制每页文本长度
                })
            
            return {
                "url": url,
                "num_pages": len(pdf_reader.pages),
                "content": text_content[:5],  # 只保留前 5 页
                "success": True
            }
        except Exception as e:
            return {"error": str(e), "success": False}
    
    @staticmethod
    def code_interpreter(code: str) -> Dict:
        """
        在完整 Python 环境中执行代码。
        不加限制地提供 Python 内置函数和标准库的访问能力。
        """
        try:
            # 去掉 markdown 代码块等格式
            import re
            
            # 去掉 ```python、```py 或 ``` 代码块围栏
            code = re.sub(r'^```(?:python|py)?\s*\n', '', code.strip())
            code = re.sub(r'\n```\s*$', '', code)
            code = re.sub(r'^```\s*', '', code)
            code = re.sub(r'\s*```$', '', code)
            
            # 同时去掉首尾空白字符
            code = code.strip()
            
            # 注意：这里刻意不做 '^' 到 '**' 的改写。'^' 是合法的 Python
            # 运算符（按位异或），一刀切的替换会悄悄改变正确代码的含义——
            # 5 ^ 3 本应是 6，被改写成 5 ** 3 后返回 125 且不报错。盲目替换
            # 还会破坏锚定的正则（r'^a.*' -> r'**a.*' 报 "nothing to repeat"），
            # 并损坏字符串字面量里的脱字符。两种 '^' 的含义无法从源码区分，
            # 因此约定改写规则写在了工具描述里。

            # 创建包含全部内置函数的完整 Python 命名空间，
            # 让 Agent 可以访问完整的 Python 环境
            import sys
            namespace = {
                '__builtins__': __builtins__,
                'math': math,
                'random': random,
                'datetime': datetime,
                'sys': sys,
                're': re,
                'json': json
            }
            
            # 同时捕获 stdout 和 stderr
            output_buffer = io.StringIO()
            error_buffer = io.StringIO()
            
            with contextlib.redirect_stdout(output_buffer), contextlib.redirect_stderr(error_buffer):
                exec(code, namespace)
            
            # 取回输出和错误信息
            printed_output = output_buffer.getvalue()
            error_output = error_buffer.getvalue()
            
            # 尝试从常见变量名取结果
            result = namespace.get('result', None)
            if result is None:
                for var_name in ['A', 'total', 'sum', 'output', 'answer', 'final', 'value']:
                    if var_name in namespace:
                        result = namespace[var_name]
                        break
            
            response = {
                "result": result,
                "output": printed_output if printed_output else None,
                "stderr": error_output if error_output else None,
                "success": True
            }
            
            return response
            
        except SyntaxError as e:
            error_msg = f"Syntax Error on line {e.lineno}: {e.msg}\n{e.text}"
            return {
                "error": error_msg,
                "error_type": "SyntaxError",
                "success": False
            }
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            return {
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": error_trace,
                "success": False
            }
    
def format_tool_response(tool_name: str, tool_result: str) -> Dict:
    """把工具响应格式化为聊天模型可用的消息"""
    return {
        "role": "tool",
        "name": tool_name,
        "content": tool_result
    }
