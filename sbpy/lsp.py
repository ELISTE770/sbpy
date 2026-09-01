"""שרת Language Server Protocol (LSP) מובנה עבור SBpy.

מאפשר לעורכי קוד (VS Code, PyCharm, Neovim, Sublime) להציג שגיאות ובאגים
בזמן אמת ולקבל Quick Fixes בלחיצה אחת, ללא שום תלות חיצונית.
פרוטוקול: JSON-RPC 2.0 מעל stdin/stdout.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, BinaryIO
from urllib.parse import unquote, urlparse

from .patcher import STATIC_FIXERS
from .static.checks import SourceUnit, analyze


def uri_to_path(uri: str) -> str:
    """ממיר file:// URI לנתיב קובץ תקין במערכת ההפעלה."""
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    if os.name == "nt" and path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path[1:]
    return os.path.abspath(path)


def path_to_uri(path: str) -> str:
    """ממיר נתיב קובץ ל-URI."""
    norm = os.path.abspath(path).replace("\\", "/")
    if os.name == "nt" and not norm.startswith("/"):
        norm = "/" + norm
    return f"file://{norm}"


@dataclass
class LSPDocument:
    uri: str
    path: str
    version: int
    text: str
    lines: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, uri: str, version: int, text: str) -> "LSPDocument":
        path = uri_to_path(uri)
        return cls(
            uri=uri,
            path=path,
            version=version,
            text=text,
            lines=text.splitlines(),
        )


SEVERITY_MAP = {
    "critical": 1,  # Error
    "error": 1,     # Error
    "warn": 2,      # Warning
    "info": 3,      # Information
}


class LSPServer:
    """שרת LSP עצמאי עבור SBpy."""

    def __init__(
        self,
        in_stream: BinaryIO | None = None,
        out_stream: BinaryIO | None = None,
    ) -> None:
        self.in_stream = in_stream if in_stream is not None else sys.stdin.buffer
        self.out_stream = out_stream if out_stream is not None else sys.stdout.buffer
        self.documents: dict[str, LSPDocument] = {}
        self.running: bool = True

    def read_message(self) -> dict[str, Any] | None:
        """קורא הודעת JSON-RPC ממוסגרת עם Content-Length."""
        content_length = -1
        while True:
            line_bytes = self.in_stream.readline()
            if not line_bytes:
                return None
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                break
            if line.lower().startswith("content-length:"):
                try:
                    content_length = int(line.split(":", 1)[1].strip())
                except ValueError:
                    content_length = -1

        if content_length <= 0:
            return None

        body_bytes = self.in_stream.read(content_length)
        if len(body_bytes) < content_length:
            return None

        try:
            return json.loads(body_bytes.decode("utf-8", errors="replace"))
        except ValueError:
            return None

    def send_message(self, message: dict[str, Any]) -> None:
        """שולח הודעת JSON-RPC עם כותרת Content-Length."""
        body = json.dumps(message, ensure_ascii=False)
        body_bytes = body.encode("utf-8")
        header = f"Content-Length: {len(body_bytes)}\r\n\r\n".encode("utf-8")
        self.out_stream.write(header + body_bytes)
        self.out_stream.flush()

    def send_response(self, req_id: Any, result: Any = None, error: Any = None) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result
        self.send_message(msg)

    def send_notification(self, method: str, params: Any) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        self.send_message(msg)

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    def handle_request(self, message: dict[str, Any]) -> None:
        req_id = message.get("id")
        method = message.get("method", "")
        params = message.get("params", {})

        if method == "initialize":
            self.send_response(
                req_id,
                result={
                    "capabilities": {
                        "textDocumentSync": 1,  # Full sync
                        "codeActionProvider": True,
                    },
                    "serverInfo": {
                        "name": "SBpy Language Server",
                        "version": "0.1.0",
                    },
                },
            )
        elif method == "initialized":
            pass
        elif method == "shutdown":
            self.send_response(req_id, result=None)
        elif method == "exit":
            self.running = False
        elif method == "textDocument/didOpen":
            doc_item = params.get("textDocument", {})
            uri = doc_item.get("uri", "")
            text = doc_item.get("text", "")
            version = doc_item.get("version", 0)
            doc = LSPDocument.create(uri, version, text)
            self.documents[uri] = doc
            self.publish_diagnostics(doc)
        elif method == "textDocument/didChange":
            doc_item = params.get("textDocument", {})
            uri = doc_item.get("uri", "")
            version = doc_item.get("version", 0)
            changes = params.get("contentChanges", [])
            if changes:
                text = changes[-1].get("text", "")
                doc = LSPDocument.create(uri, version, text)
                self.documents[uri] = doc
                self.publish_diagnostics(doc)
        elif method == "textDocument/didSave":
            doc_item = params.get("textDocument", {})
            uri = doc_item.get("uri", "")
            doc = self.documents.get(uri)
            if doc is not None:
                self.publish_diagnostics(doc)
        elif method == "textDocument/didClose":
            doc_item = params.get("textDocument", {})
            uri = doc_item.get("uri", "")
            self.documents.pop(uri, None)
            self.send_notification("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": []})
        elif method == "textDocument/codeAction":
            actions = self.handle_code_action(params)
            self.send_response(req_id, result=actions)
        else:
            if req_id is not None:
                self.send_response(req_id, result=None)

    def publish_diagnostics(self, doc: LSPDocument) -> None:
        """מריץ את הניתוח הסטטי ושולח את כל הממצאים כ-Diagnostics ל-LSP Client."""
        unit = SourceUnit.from_source(doc.text, filename=doc.path)
        findings = analyze(unit)
        diagnostics: list[dict[str, Any]] = []

        for f in findings:
            line_idx = max(0, f.line - 1)
            col_idx = max(0, f.col)
            line_text = doc.lines[line_idx] if line_idx < len(doc.lines) else ""
            end_col = len(line_text)

            diagnostics.append(
                {
                    "range": {
                        "start": {"line": line_idx, "character": col_idx},
                        "end": {"line": line_idx, "character": end_col},
                    },
                    "severity": SEVERITY_MAP.get(f.severity, 2),
                    "code": f.rule,
                    "source": "SBpy",
                    "message": f.message + (f" ({f.hint})" if f.hint else ""),
                }
            )

        self.send_notification(
            "textDocument/publishDiagnostics",
            {
                "uri": doc.uri,
                "version": doc.version,
                "diagnostics": diagnostics,
            },
        )

    def handle_code_action(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """מייצר QuickFix Actions עבור הממצאים בטווח המסומן."""
        doc_item = params.get("textDocument", {})
        uri = doc_item.get("uri", "")
        doc = self.documents.get(uri)
        if doc is None:
            return []

        unit = SourceUnit.from_source(doc.text, filename=doc.path)
        findings = analyze(unit)
        actions: list[dict[str, Any]] = []

        for f in findings:
            fixer = STATIC_FIXERS.get(f.rule)
            if fixer is None or not (1 <= f.line <= len(doc.lines)):
                continue

            original = doc.lines[f.line - 1]
            updated = fixer(original, f)
            if updated is None or updated == [original]:
                continue

            target_line_idx = max(0, f.line - 1)
            replacement_text = "\n".join(updated)
            if target_line_idx < len(doc.lines):
                # מחליפים את השורה הישנה
                end_line_idx = target_line_idx + 1
                end_char_idx = 0
            else:
                end_line_idx = target_line_idx
                end_char_idx = len(doc.lines[target_line_idx]) if doc.lines else 0

            text_edit = {
                "range": {
                    "start": {"line": target_line_idx, "character": 0},
                    "end": {"line": end_line_idx, "character": end_char_idx},
                },
                "newText": replacement_text + ("\n" if target_line_idx < len(doc.lines) else ""),
            }

            actions.append(
                {
                    "title": f"SBpy Fix: {f.message}",
                    "kind": "quickfix",
                    "isPreferred": True,
                    "edit": {
                        "changes": {
                            uri: [text_edit],
                        }
                    },
                }
            )

        return actions

    def run(self) -> None:
        """לולאת השרת הראשית."""
        while self.running:
            msg = self.read_message()
            if msg is None:
                break
            self.handle_request(msg)


def start_lsp_server() -> None:
    """נקודת כניסה להפעלת שרת ה-LSP משורת הפקודה."""
    server = LSPServer()
    server.run()
