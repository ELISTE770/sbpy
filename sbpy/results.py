"""מבני הנתונים שכל שכבות SBpy מחזירות."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Literal

Source = Literal["local", "static", "cache", "gemini", "none"]
Severity = Literal["info", "warn", "error", "critical"]

# דירוג מקורות – ככל שגבוה יותר, כך "יקר" יותר להשיג
SOURCE_COST: dict[str, int] = {
    "none": 0,
    "local": 1,
    "static": 1,
    "cache": 2,
    "gemini": 3,
}


@dataclass
class Diagnosis:
    """אבחנה אחת לגבי שגיאה."""

    title: str
    detail: str = ""
    suggestion: str = ""
    confidence: float = 0.0
    source: Source = "local"
    rule: str = ""
    patch: str | None = None
    """קטע קוד מוצע להחלפה (אופציונלי)."""

    auto_fix: Callable[[], Any] | None = field(default=None, repr=False, compare=False)
    """אם קיים – ניתן להריץ תיקון אוטומטי בטוח (משמש ל-@smart(retry=True))."""

    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.72

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("auto_fix", None)
        return data


@dataclass
class Finding:
    """ממצא סטטי בקוד (משמש את @SFB / @SEC / @OPT ...)."""

    rule: str
    message: str
    line: int
    col: int = 0
    severity: Severity = "warn"
    file: str = ""
    hint: str = ""
    snippet: str = ""
    source: Source = "static"
    confidence: float = 0.9

    symbol: str = ""
    """The exact name the finding is about, when the rule targets one name.

    A fix must never act on the whole line when only one name on it is at
    fault - that is how `from x import A, B` loses A.
    """

    def location(self) -> str:
        base = self.file or "<code>"
        return f"{base}:{self.line}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    """התוצאה המלאה של ריצת סולם ההסלמה על שגיאה אחת."""

    exc_type: str = ""
    exc_message: str = ""
    fingerprint: str = ""
    where: str = ""
    file: str = ""
    diagnoses: list[Diagnosis] = field(default_factory=list)
    escalated: bool = False
    escalation_reason: str = ""
    skipped_reason: str = ""
    tokens: int = 0
    elapsed_ms: int = 0
    snippet_lines: list[tuple[int, str]] = field(default_factory=list)
    snippet_mark: int = 0

    @property
    def best(self) -> Diagnosis | None:
        if not self.diagnoses:
            return None
        return max(self.diagnoses, key=lambda d: (d.confidence, SOURCE_COST.get(d.source, 0)))

    @property
    def top_confidence(self) -> float:
        best = self.best
        return best.confidence if best else 0.0

    def add(self, diagnosis: Diagnosis | None) -> None:
        if diagnosis is not None:
            self.diagnoses.append(diagnosis)

    def sorted_diagnoses(self) -> list[Diagnosis]:
        return sorted(
            self.diagnoses,
            key=lambda d: (-d.confidence, SOURCE_COST.get(d.source, 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "exc_type": self.exc_type,
            "exc_message": self.exc_message,
            "fingerprint": self.fingerprint,
            "where": self.where,
            "file": self.file,
            "escalated": self.escalated,
            "escalation_reason": self.escalation_reason,
            "skipped_reason": self.skipped_reason,
            "tokens": self.tokens,
            "elapsed_ms": self.elapsed_ms,
            "diagnoses": [d.to_dict() for d in self.diagnoses],
        }


@dataclass
class ScanResult:
    """התוצאה של ריצת קיצור־דרך (@SFB וכו') על קובץ/קוד."""

    shortcut: str
    target: str
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    escalated: bool = False
    escalation_reason: str = ""
    text: str = ""
    """פלט חופשי מ-Gemini עבור קיצורים שאינם רשימת ממצאים (למשל @EXP)."""

    tokens: int = 0

    def __len__(self) -> int:
        return len(self.findings)

    def __bool__(self) -> bool:
        return bool(self.findings or self.text)

    def dedupe(self) -> int:
        """Removes repeated findings. Returns how many were dropped.

        A project-wide analysis can legitimately surface the same finding
        more than once; the user should still see it once.
        """
        seen: set[tuple[str, int, int, str, str]] = set()
        unique: list[Finding] = []
        for finding in self.findings:
            key = (finding.file, finding.line, finding.col, finding.rule, finding.message)
            if key in seen:
                continue
            seen.add(key)
            unique.append(finding)
        dropped = len(self.findings) - len(unique)
        self.findings = unique
        return dropped

    def by_severity(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {}
        for finding in self.findings:
            out.setdefault(finding.severity, []).append(finding)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "shortcut": self.shortcut,
            "target": self.target,
            "escalated": self.escalated,
            "escalation_reason": self.escalation_reason,
            "tokens": self.tokens,
            "notes": self.notes,
            "text": self.text,
            "findings": [f.to_dict() for f in self.findings],
        }
