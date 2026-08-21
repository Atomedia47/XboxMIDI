"""
Orchestrator — the brain that routes messages between agents, manages
recursive learning loops, and tracks everything for the monitor.

Recursive learning flow:
  1. User (or a trigger) sends a prompt to an agent
  2. That agent responds and optionally routes to another agent
  3. The receiving agent processes, responds, and may route further
  4. At each step, the orchestrator extracts learnings and feeds them back
  5. The cycle continues until a termination condition is met
     (max depth, convergence, or explicit stop)
"""

import json
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Callable
from .agent import Agent, Message, LearningEntry


@dataclass
class ConversationChain:
    id: str = ""
    messages: list[Message] = field(default_factory=list)
    agents_involved: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    status: str = "active"  # active, completed, stopped
    depth: int = 0
    max_depth: int = 10
    learnings_produced: int = 0


class Orchestrator:
    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.chains: list[ConversationChain] = []
        self.event_log: list[dict] = []
        self.routes: dict[str, list[str]] = {}  # agent_name -> [target_agents]
        self.lock = threading.Lock()
        self._chain_counter = 0

    def register_agent(self, agent: Agent):
        with self.lock:
            self.agents[agent.name] = agent
            self._log_event("agent_registered", {
                "name": agent.name,
                "role": agent.role,
                "model": agent.model_config.get("model"),
            })

    def set_route(self, source: str, targets: list[str]):
        self.routes[source] = targets

    def remove_agent(self, name: str):
        with self.lock:
            if name in self.agents:
                del self.agents[name]
                self._log_event("agent_removed", {"name": name})

    def send_message(self, sender: str, recipient: str, content: str) -> Optional[Message]:
        if recipient not in self.agents:
            self._log_event("message_failed", {
                "sender": sender,
                "recipient": recipient,
                "reason": "agent not found",
            })
            return None

        msg = Message(sender=sender, recipient=recipient, content=content)
        agent = self.agents[recipient]
        reply = agent.receive(msg)
        self._log_event("message_exchanged", {
            "sender": sender,
            "recipient": recipient,
            "reply_preview": reply.content[:200],
            "tokens": reply.metadata,
        })
        return reply

    def recursive_prompt(
        self,
        initial_sender: str,
        initial_recipient: str,
        prompt: str,
        max_depth: int = 10,
        on_message: Optional[Callable] = None,
    ) -> ConversationChain:
        """
        Kick off a recursive learning chain. The initial prompt goes to
        initial_recipient, and the response gets routed to the next agent
        in the chain based on configured routes.

        on_message callback fires for each exchange so the monitor can
        stream updates in real time.
        """
        self._chain_counter += 1
        chain = ConversationChain(
            id=f"chain-{self._chain_counter:04d}",
            max_depth=max_depth,
            agents_involved=[initial_sender, initial_recipient],
        )

        current_sender = initial_sender
        current_recipient = initial_recipient
        current_content = prompt

        for depth in range(max_depth):
            chain.depth = depth + 1

            if current_recipient not in self.agents:
                chain.status = "stopped"
                self._log_event("chain_stopped", {
                    "chain_id": chain.id,
                    "reason": f"agent '{current_recipient}' not found",
                    "depth": depth,
                })
                break

            msg = Message(
                sender=current_sender,
                recipient=current_recipient,
                content=current_content,
            )
            chain.messages.append(msg)

            reply = self.agents[current_recipient].receive(msg)
            chain.messages.append(reply)

            if on_message:
                on_message(chain, msg, reply)

            self._extract_learning(chain, reply)

            # Determine next hop
            next_targets = self.routes.get(current_recipient, [])
            if not next_targets:
                chain.status = "completed"
                self._log_event("chain_completed", {
                    "chain_id": chain.id,
                    "depth": depth + 1,
                    "learnings": chain.learnings_produced,
                })
                break

            current_sender = current_recipient
            current_recipient = next_targets[depth % len(next_targets)]
            current_content = reply.content

            if current_recipient not in chain.agents_involved:
                chain.agents_involved.append(current_recipient)
        else:
            chain.status = "completed"
            self._log_event("chain_completed", {
                "chain_id": chain.id,
                "depth": max_depth,
                "reason": "max_depth reached",
                "learnings": chain.learnings_produced,
            })

        with self.lock:
            self.chains.append(chain)
        return chain

    def _extract_learning(self, chain: ConversationChain, reply: Message):
        """
        Pull structured learnings from agent responses. Agents can embed
        learnings with [LEARNING: ...] tags in their output, or we can
        extract key insights automatically.
        """
        content = reply.content
        learning_markers = []

        # Look for explicit learning tags
        import re
        for match in re.finditer(r'\[LEARNING:\s*(.+?)\]', content, re.DOTALL):
            learning_markers.append(match.group(1).strip())

        # Look for insight tags
        for match in re.finditer(r'\[INSIGHT:\s*(.+?)\]', content, re.DOTALL):
            learning_markers.append(match.group(1).strip())

        for insight in learning_markers:
            # Feed learning to all agents in the chain
            for agent_name in chain.agents_involved:
                if agent_name in self.agents and agent_name != reply.sender:
                    self.agents[agent_name].learn(
                        source_agent=reply.sender,
                        insight=insight,
                        confidence=0.8,
                        context=f"chain:{chain.id}",
                    )
            chain.learnings_produced += 1

    def multi_agent_discussion(
        self,
        participants: list[str],
        topic: str,
        rounds: int = 5,
        on_message: Optional[Callable] = None,
    ) -> ConversationChain:
        """
        Round-robin discussion: each agent responds to the previous agent's
        message, building on the conversation. Like ZEMA prompting Overseer,
        Overseer prompting Captain, Captain back to Overseer, etc.
        """
        self._chain_counter += 1
        chain = ConversationChain(
            id=f"discussion-{self._chain_counter:04d}",
            max_depth=rounds * len(participants),
            agents_involved=list(participants),
        )

        current_content = topic
        current_sender = "user"

        for round_num in range(rounds):
            for i, agent_name in enumerate(participants):
                if agent_name not in self.agents:
                    continue

                chain.depth += 1
                msg = Message(
                    sender=current_sender,
                    recipient=agent_name,
                    content=current_content,
                )
                chain.messages.append(msg)

                reply = self.agents[agent_name].receive(msg)
                chain.messages.append(reply)

                if on_message:
                    on_message(chain, msg, reply)

                self._extract_learning(chain, reply)

                current_sender = agent_name
                current_content = reply.content

        chain.status = "completed"
        with self.lock:
            self.chains.append(chain)
        return chain

    def get_all_status(self) -> dict:
        with self.lock:
            return {
                "agents": {
                    name: agent.get_status()
                    for name, agent in self.agents.items()
                },
                "active_chains": sum(
                    1 for c in self.chains if c.status == "active"
                ),
                "completed_chains": sum(
                    1 for c in self.chains if c.status == "completed"
                ),
                "total_events": len(self.event_log),
                "recent_events": [e for e in self.event_log[-20:]],
            }

    def get_chain_history(self, limit: int = 10) -> list[dict]:
        chains = self.chains[-limit:]
        return [
            {
                "id": c.id,
                "status": c.status,
                "depth": c.depth,
                "agents": c.agents_involved,
                "learnings": c.learnings_produced,
                "messages": len(c.messages),
                "started": c.started,
            }
            for c in chains
        ]

    def _log_event(self, event_type: str, data: dict):
        event = {
            "type": event_type,
            "timestamp": time.time(),
            "data": data,
        }
        with self.lock:
            self.event_log.append(event)
            if len(self.event_log) > 1000:
                self.event_log = self.event_log[-500:]
