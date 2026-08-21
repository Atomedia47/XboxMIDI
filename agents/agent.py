"""
Base agent class — every bot (ZEMA, Overseer, Captain, Odysseus, Xoma, BMO)
is an Agent with a role, a system prompt, a memory, and a model backend.
"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional
from .models import ModelResponse, get_backend


@dataclass
class Message:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    sender: str = ""
    recipient: str = ""
    content: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "sender": self.sender,
            "recipient": self.recipient,
            "content": self.content,
            "metadata": self.metadata,
        }


@dataclass
class LearningEntry:
    timestamp: float = field(default_factory=time.time)
    source_agent: str = ""
    insight: str = ""
    confidence: float = 0.0
    context: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "source_agent": self.source_agent,
            "insight": self.insight,
            "confidence": self.confidence,
            "context": self.context,
        }


class Agent:
    def __init__(self, name: str, role: str, system_prompt: str, model_config: dict):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.backend = get_backend(model_config)
        self.model_config = model_config
        self.conversation_history: list[dict] = []
        self.learnings: list[LearningEntry] = []
        self.message_log: list[Message] = []
        self.active = True
        self.stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "tokens_in_total": 0,
            "tokens_out_total": 0,
            "learning_entries": 0,
        }

    def receive(self, message: Message) -> Message:
        self.message_log.append(message)
        self.stats["messages_received"] += 1

        self.conversation_history.append({
            "role": "user",
            "content": f"[From {message.sender}]: {message.content}",
        })

        learnings_context = ""
        if self.learnings:
            recent = self.learnings[-5:]
            learnings_context = "\n\nRecent learnings:\n" + "\n".join(
                f"- [{e.source_agent}] {e.insight} (confidence: {e.confidence:.1f})"
                for e in recent
            )

        system = self.system_prompt + learnings_context
        response = self.backend.chat(self.conversation_history, temperature=0.7)

        self.stats["tokens_in_total"] += response.tokens_in
        self.stats["tokens_out_total"] += response.tokens_out

        self.conversation_history.append({
            "role": "assistant",
            "content": response.text,
        })

        # Trim history to last 50 exchanges to keep context manageable
        if len(self.conversation_history) > 100:
            self.conversation_history = self.conversation_history[-100:]

        reply = Message(
            sender=self.name,
            recipient=message.sender,
            content=response.text,
            metadata={
                "model": response.model,
                "tokens_in": response.tokens_in,
                "tokens_out": response.tokens_out,
                "latency_ms": response.latency_ms,
            },
        )
        self.message_log.append(reply)
        self.stats["messages_sent"] += 1
        return reply

    def learn(self, source_agent: str, insight: str, confidence: float, context: str = ""):
        entry = LearningEntry(
            source_agent=source_agent,
            insight=insight,
            confidence=confidence,
            context=context,
        )
        self.learnings.append(entry)
        self.stats["learning_entries"] += 1

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "active": self.active,
            "model": self.model_config.get("model", "unknown"),
            "backend": self.model_config.get("backend", "unknown"),
            "stats": self.stats.copy(),
            "learnings_count": len(self.learnings),
            "history_length": len(self.conversation_history),
        }
