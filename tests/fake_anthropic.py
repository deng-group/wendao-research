"""A local stand-in for the Anthropic Messages API, for tests without network: scripted replies, streamed as SSE."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


class FakeAnthropic:
    """`replies` is a list of turns; each turn is a list of content blocks: {"text": ...} or {"tool": name, "input": {...}}."""

    def __init__(self, replies: list[list[dict]]):
        self.replies = list(replies)
        self.requests: list[dict] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                turn = fake.replies.pop(0) if fake.replies else [{"text": "(no more scripted replies)"}]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                has_tool = any("tool" in block for block in turn)
                self.wfile.write(sse("message_start", {"type": "message_start", "message": {
                    "id": "msg_1", "type": "message", "role": "assistant", "model": body.get("model", "fake"), "content": [],
                    "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}}))
                for index, block in enumerate(turn):
                    if "text" in block:
                        self.wfile.write(sse("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}}))
                        for piece in [block["text"][i:i + 12] for i in range(0, len(block["text"]), 12)]:
                            self.wfile.write(sse("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": piece}}))
                    else:
                        self.wfile.write(sse("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "tool_use", "id": f"toolu_{index}", "name": block["tool"], "input": {}}}))
                        self.wfile.write(sse("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}}))
                    self.wfile.write(sse("content_block_stop", {"type": "content_block_stop", "index": index}))
                self.wfile.write(sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use" if has_tool else "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 5}}))
                self.wfile.write(sse("message_stop", {"type": "message_stop"}))
                self.wfile.flush()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
