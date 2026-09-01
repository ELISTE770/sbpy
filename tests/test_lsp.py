"""בדיקות עבור שרת ה-LSP של SBpy."""

from __future__ import annotations

import io
import json
import unittest

from sbpy.lsp import LSPServer


class LSPTest(unittest.TestCase):
    def test_lsp_lifecycle_and_diagnostics(self) -> None:
        in_buffer = io.BytesIO()
        out_buffer = io.BytesIO()

        # ניצור הודעות: initialize -> didOpen (עם באג) -> codeAction -> shutdown -> exit
        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {
                "jsonrpc": "2.0",
                "method": "textDocument/didOpen",
                "params": {
                    "textDocument": {
                        "uri": "file:///test.py",
                        "version": 1,
                        "text": "try:\n    pass\nexcept:\n    pass\n",
                    }
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "textDocument/codeAction",
                "params": {
                    "textDocument": {"uri": "file:///test.py"},
                    "range": {
                        "start": {"line": 2, "character": 0},
                        "end": {"line": 3, "character": 0},
                    },
                },
            },
            {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": {}},
            {"jsonrpc": "2.0", "method": "exit", "params": {}},
        ]

        for msg in messages:
            body = json.dumps(msg).encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
            in_buffer.write(header + body)

        in_buffer.seek(0)
        server = LSPServer(in_stream=in_buffer, out_stream=out_buffer)
        server.run()

        # נקרא את כל התשובות שנכתבו ל-out_buffer
        out_buffer.seek(0)
        output_bytes = out_buffer.read()
        self.assertIn(b"SBpy Language Server", output_bytes)
        self.assertIn(b"textDocument/publishDiagnostics", output_bytes)
        self.assertIn(b"bare-except", output_bytes)
        self.assertIn(b"quickfix", output_bytes)


if __name__ == "__main__":
    unittest.main()
