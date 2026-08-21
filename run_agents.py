#!/usr/bin/env python3
"""
Quick launcher for the multi-bot recursive learning system.

Usage:
  python3 run_agents.py                    # Start the server + monitor
  python3 run_agents.py --port 8080        # Custom port
  python3 run_agents.py --config my.json   # Custom config
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents.server import load_config, build_orchestrator, HTTPServer, APIHandler
import agents.server as srv


def main():
    parser = argparse.ArgumentParser(description="Multi-Bot Recursive Learning System")
    parser.add_argument("--port", type=int, default=None, help="Monitor port (default: from config)")
    parser.add_argument("--config", type=str, default=None, help="Config file path")
    args = parser.parse_args()

    config = load_config(args.config)
    port = args.port or config.get("defaults", {}).get("monitor_port", 7777)

    srv._config = config
    srv._orchestrator = build_orchestrator(config)

    print("=" * 50)
    print("  MULTI-BOT RECURSIVE LEARNING SYSTEM")
    print("=" * 50)
    print()
    print(f"  Monitor:  http://0.0.0.0:{port}")
    print(f"  API:      http://0.0.0.0:{port}/api/status")
    print()
    print("  Agents loaded:")
    for name, agent in srv._orchestrator.agents.items():
        print(f"    - {name} ({agent.role})")
    print()
    print("  Routes:")
    for source, targets in srv._orchestrator.routes.items():
        print(f"    {source} -> {', '.join(targets)}")
    print()
    print("  Open the monitor URL on your phone to watch.")
    print("  Press Ctrl+C to stop.")
    print()

    server = HTTPServer(("0.0.0.0", port), APIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
