"""Drive assistant.stream_chat with a fake Anthropic client: tool call -> DB result -> streamed answer."""
import json
from types import SimpleNamespace as NS

import anthropic

from app import assistant
from app.database import SessionLocal


class FakeStream:
    def __init__(self, final, texts):
        self.final, self.texts = final, texts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(NS(type="text", text=t) for t in self.texts)

    def get_final_message(self):
        return self.final


class FakeClient:
    def __init__(self, **_):
        self.calls = []
        self.beta = NS(messages=NS(stream=self.stream))

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            block = NS(type="tool_use", id="tu_1", name="find_nearest_gym", input={})
            return FakeStream(NS(stop_reason="tool_use", content=[block]), [])
        return FakeStream(NS(stop_reason="end_turn", content=[NS(type="text", text="Misty is closest.")]),
                          ["Misty ", "is closest."])


def test_tool_loop_streams_answer(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(assistant, "ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: fake)
    db = SessionLocal()
    ctx = {"location": {"region": "kanto", "x": 580, "y": 160, "label": "Cerulean City"}}
    events = list(assistant.stream_chat(db, [{"role": "user", "content": "nearest gym?"}], ctx))
    db.close()

    assert any('"name": "find_nearest_gym"' in e for e in events if e.startswith("event: tool"))
    text = "".join(json.loads(e.split("data: ", 1)[1])["delta"] for e in events if e.startswith("event: text"))
    assert text == "Misty is closest."
    assert events[-1].startswith("event: done")

    second = fake.calls[1]
    tool_result = second["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and "Misty" in tool_result["content"]
    assert second["model"] == assistant.CLAUDE_MODEL and second["tools"] == assistant.TOOLS
