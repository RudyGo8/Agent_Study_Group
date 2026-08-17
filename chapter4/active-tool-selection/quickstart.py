"""
Quick Start for Active Tool Selection.

Run this script to see a basic demonstration of active tool discovery.
"""

from agent import ActiveToolAgent, PassiveToolAgent
from tool_knowledge_base import create_tool_knowledge_base, calculate_total_tokens


def main():
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                                                                            ║
║                  Active Tool Selection - Quick Start                       ║
║                  Inspired by MCP-Zero (arXiv:2506.01056)                  ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝

This demonstration shows how active tool discovery enables agents to:
  • Maintain minimal context footprint
  • Actively request tools as needed
  • Scale efficiently with ecosystem growth

""")
    
    # Show knowledge base info
    print("📚 Tool Knowledge Base:")
    servers = create_tool_knowledge_base()
    total_tools = sum(len(server.tools) for server in servers)
    total_tokens = calculate_total_tokens([tool for server in servers for tool in server.tools])
    
    print(f"   • Servers: {len(servers)}")
    print(f"   • Total tools: {total_tools}")
    print(f"   • Token cost if all injected: ~{total_tokens:,} tokens")
    print()
    
    # Example task
    task = "Search for Python web frameworks on GitHub with more than 5000 stars"
    print(f"🎯 Example Task:\n   {task}\n")
    
    # Test with active agent
    print("=" * 80)
    print("1️⃣  ACTIVE TOOL DISCOVERY")
    print("=" * 80)
    print("\n⏳ Agent is analyzing task and discovering needed tools...\n")
    
    active_agent = ActiveToolAgent()
    active_result = active_agent.execute_task(task)
    
    print(f"✅ Task completed with active discovery:\n")
    print(f"   📊 Metrics:")
    print(f"      • Tools loaded: {active_result['metrics']['tools_loaded']} (out of {total_tools})")
    print(f"      • Tokens used: {active_result['metrics']['tokens_used']:,}")
    print(f"      • Tool requests: {active_result['metrics']['tool_requests']}")
    print(f"      • API calls: {active_result['metrics']['api_calls']}")
    print()
    print(f"   🛠️  Tools discovered:")
    for tool in active_result['tools_loaded']:
        print(f"      • {tool}")
    print()
    
    # Test with passive agent
    print("=" * 80)
    print("2️⃣  PASSIVE TOOL INJECTION (Traditional Approach)")
    print("=" * 80)
    print(f"\n⏳ Agent has all {total_tools} tools pre-loaded...\n")
    
    passive_agent = PassiveToolAgent()
    passive_result = passive_agent.execute_task(task)
    
    print(f"✅ Task completed with passive injection:\n")
    print(f"   📊 Metrics:")
    print(f"      • Tools loaded: {passive_result['metrics']['tools_loaded']} (all tools)")
    print(f"      • Tokens used: {passive_result['metrics']['tokens_used']:,}")
    print(f"      • API calls: {passive_result['metrics']['api_calls']}")
    print()
    
    # Comparison
    print("=" * 80)
    print("3️⃣  COMPARISON")
    print("=" * 80)
    print()
    
    token_reduction = (1 - active_result['metrics']['tokens_used'] / 
                       passive_result['metrics']['tokens_used']) * 100
    tool_reduction = (1 - active_result['metrics']['tools_loaded'] / 
                      passive_result['metrics']['tools_loaded']) * 100
    
    print(f"📊 Efficiency Gains:\n")
    print(f"   Token Usage:")
    print(f"      • Active: {active_result['metrics']['tokens_used']:,} tokens")
    print(f"      • Passive: {passive_result['metrics']['tokens_used']:,} tokens")
    print(f"      • Reduction: {token_reduction:.1f}% 🎉")
    print()
    print(f"   Tools Loaded:")
    print(f"      • Active: {active_result['metrics']['tools_loaded']} tools")
    print(f"      • Passive: {passive_result['metrics']['tools_loaded']} tools")
    print(f"      • Reduction: {tool_reduction:.1f}% 🎯")
    print()
    
    print("=" * 80)
    print("💡 KEY INSIGHTS")
    print("=" * 80)
    print("""
1. Active Discovery maintains agent autonomy
   → Agent decides what tools it needs, when it needs them

2. Massive efficiency gains
   → 80-98% token reduction for typical tasks

3. Scales with ecosystem growth
   → Adding 100 more tools doesn't bloat every request

4. Iterative capability extension
   → Toolchain evolves as task understanding deepens

5. Semantic routing enables precision
   → Tools matched by meaning, not just keywords

""")
    
    print("🎓 Next Steps:")
    print("   • Run 'python demo_comparison.py' for comprehensive comparison")
    print("   • Run 'python examples.py' for more use cases")
    print("   • See README.md for architecture details")
    print()
    print("📄 Reference: MCP-Zero paper - https://arxiv.org/pdf/2506.01056")
    print()


if __name__ == "__main__":
    main()
