"""
HTTP server — serves the monitor dashboard and provides a JSON API
for real-time agent status, chain history, and control.

Run: python3 -m agents.server
Access from phone: http://<your-ip>:7777
"""

import json
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from .orchestrator import Orchestrator
from .agent import Agent


def load_config(path: str = None) -> dict:
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config", "agents.json")
    with open(path) as f:
        return json.load(f)


def build_orchestrator(config: dict) -> Orchestrator:
    orch = Orchestrator()
    for key, agent_cfg in config.get("agents", {}).items():
        agent = Agent(
            name=agent_cfg["name"],
            role=agent_cfg["role"],
            system_prompt=agent_cfg["system_prompt"],
            model_config=agent_cfg["model"],
        )
        orch.register_agent(agent)

    for source, targets in config.get("routes", {}).items():
        name_map = {k: v["name"] for k, v in config["agents"].items()}
        source_name = name_map.get(source, source)
        target_names = [name_map.get(t, t) for t in targets]
        orch.set_route(source_name, target_names)

    return orch


# Global orchestrator instance
_orchestrator: Orchestrator = None
_config: dict = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator, _config
    if _orchestrator is None:
        _config = load_config()
        _orchestrator = build_orchestrator(_config)
    return _orchestrator


class APIHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress default logging

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, data, status=200):
        body = json.dumps(data, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _html_response(self, html):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(html.encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        orch = get_orchestrator()

        if path == "/" or path == "/monitor":
            monitor_path = os.path.join(
                os.path.dirname(__file__), "..", "monitor", "index.html"
            )
            with open(monitor_path) as f:
                self._html_response(f.read())

        elif path == "/api/status":
            self._json_response(orch.get_all_status())

        elif path == "/api/chains":
            limit = int(params.get("limit", [10])[0])
            self._json_response(orch.get_chain_history(limit))

        elif path == "/api/agents":
            agents_status = {
                name: agent.get_status()
                for name, agent in orch.agents.items()
            }
            self._json_response(agents_status)

        elif path.startswith("/api/agent/"):
            agent_name = path.split("/")[-1]
            if agent_name in orch.agents:
                status = orch.agents[agent_name].get_status()
                status["recent_messages"] = [
                    m.to_dict() for m in orch.agents[agent_name].message_log[-20:]
                ]
                status["learnings"] = [
                    l.to_dict() for l in orch.agents[agent_name].learnings[-20:]
                ]
                self._json_response(status)
            else:
                self._json_response({"error": "agent not found"}, 404)

        elif path == "/api/events":
            limit = int(params.get("limit", [50])[0])
            events = orch.event_log[-limit:]
            self._json_response(events)

        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        orch = get_orchestrator()

        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            body = json.loads(self.rfile.read(content_length))

        if path == "/api/message":
            sender = body.get("sender", "user")
            recipient = body.get("recipient", "")
            content = body.get("content", "")
            if not recipient or not content:
                self._json_response({"error": "recipient and content required"}, 400)
                return
            reply = orch.send_message(sender, recipient, content)
            if reply:
                self._json_response(reply.to_dict())
            else:
                self._json_response({"error": "delivery failed"}, 500)

        elif path == "/api/recursive":
            sender = body.get("sender", "user")
            recipient = body.get("recipient", "")
            prompt = body.get("prompt", "")
            max_depth = body.get("max_depth", 10)
            if not recipient or not prompt:
                self._json_response({"error": "recipient and prompt required"}, 400)
                return

            def run_chain():
                orch.recursive_prompt(sender, recipient, prompt, max_depth)

            threading.Thread(target=run_chain, daemon=True).start()
            self._json_response({"status": "started", "recipient": recipient})

        elif path == "/api/discussion":
            participants = body.get("participants", [])
            topic = body.get("topic", "")
            rounds = body.get("rounds", 5)
            if not participants or not topic:
                self._json_response(
                    {"error": "participants and topic required"}, 400
                )
                return

            def run_discussion():
                orch.multi_agent_discussion(participants, topic, rounds)

            threading.Thread(target=run_discussion, daemon=True).start()
            self._json_response({
                "status": "started",
                "participants": participants,
                "rounds": rounds,
            })

        elif path == "/api/stop":
            agent_name = body.get("agent", "")
            if agent_name in orch.agents:
                orch.agents[agent_name].active = False
                self._json_response({"status": "stopped", "agent": agent_name})
            else:
                self._json_response({"error": "agent not found"}, 404)

        else:
            self._json_response({"error": "not found"}, 404)


def main():
    config = load_config()
    port = config.get("defaults", {}).get("monitor_port", 7777)
    global _orchestrator, _config
    _config = config
    _orchestrator = build_orchestrator(config)

    server = HTTPServer(("0.0.0.0", port), APIHandler)
    print(f"Multi-Bot Recursive Learning System")
    print(f"Monitor: http://0.0.0.0:{port}")
    print(f"API:     http://0.0.0.0:{port}/api/status")
    print(f"Agents:  {', '.join(_orchestrator.agents.keys())}")
    print(f"\nReady. Open the monitor URL on your phone to watch.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
