"""Offline mock LLM endpoint for harness integration tests (M1 task-injection spike).

Serves an OpenAI-compatible /chat/completions that replays a pre-scripted
sequence of assistant turns (tool calls, then a final message). Lets us drive
EnterpriseOps-Gym's evaluate.py end-to-end with zero API keys and a fully
deterministic policy, so the spike isolates HARNESS behavior from model behavior.

Usage:
    python scripted_responder.py --script script.json --port 8099

script.json: a JSON list; each element is one assistant turn:
    {"tool_calls": [{"name": "<tool>", "arguments": {...}}]}
  or
    {"content": "final answer text"}

Turn selection: the n-th assistant turn is chosen where n = number of messages
with role "tool" in the incoming request (correct for a sequential ReAct loop).
Requests beyond the script length get a plain stop message.
"""

import argparse
import json
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPT = []


def build_response(turn: dict, model: str) -> dict:
    message = {"role": "assistant", "content": turn.get("content")}
    finish_reason = "stop"
    if "tool_calls" in turn:
        message["content"] = turn.get("content") or None
        message["tool_calls"] = [
            {
                "id": f"call_{uuid.uuid4().hex[:24]}",
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": json.dumps(tc["arguments"]),
                },
            }
            for tc in turn["tool_calls"]
        ]
        finish_reason = "tool_calls"
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {"index": 0, "message": message, "finish_reason": finish_reason}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not self.path.rstrip("/").endswith("chat/completions"):
            self.send_error(404, f"unexpected path {self.path}")
            return
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        n_tool_msgs = sum(1 for m in req.get("messages", []) if m.get("role") == "tool")
        if n_tool_msgs < len(SCRIPT):
            turn = SCRIPT[n_tool_msgs]
        else:
            turn = {"content": "Script exhausted; stopping."}
        body = json.dumps(build_response(turn, req.get("model", "scripted"))).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quiet
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", required=True)
    ap.add_argument("--port", type=int, default=8099)
    args = ap.parse_args()
    global SCRIPT
    with open(args.script) as f:
        SCRIPT = json.load(f)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"scripted responder on 127.0.0.1:{args.port}, {len(SCRIPT)} turns")
    server.serve_forever()


if __name__ == "__main__":
    main()
