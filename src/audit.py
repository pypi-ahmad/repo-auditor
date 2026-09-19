"""Auditor module: three Agnes passes merging findings JSON and optional static checks."""

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Callable, Dict, List, Optional
from openai import OpenAI

from src.pack import PackResult
from src.providers import create_openai_client


PASS_INSTRUCTIONS = {
    "breaking_api": (
        "Pass 1: Breaking API / Call-Site Drift Auditor\n"
        "Analyze the provided repository files for breaking API changes, renamed or removed functions, "
        "and call-site drift. Specifically check if any module imports or calls a symbol that has been "
        "renamed, modified, or removed in another file (e.g., b.py imports or calls a missing name from a.py).\n\n"
        "Return a JSON array of findings with this exact schema:\n"
        "[\n"
        "  {\n"
        '    "severity": "High" | "Medium" | "Low" | "Info",\n'
        '    "file": "path/to/affected/file",\n'
        '    "title": "Concise summary of break or drift",\n'
        '    "evidence_span": "Exact function name, line reference, or code snippet showing the break",\n'
        '    "recommendation": "How to resolve the break"\n'
        "  }\n"
        "]\n"
        "Return ONLY valid JSON. If no issues found, return []."
    ),
    "security": (
        "Pass 2: Security & Credentials Auditor\n"
        "Analyze the provided repository files for security vulnerabilities: injection risks (SQL, "
        "command, path traversal, LDAP), and hardcoded secrets/credentials/tokens patterns.\n"
        "SAFETY MANDATE: Report locations only. DO NOT write exploits, attack payloads, or weaponized instructions.\n\n"
        "Return a JSON array of findings with this exact schema:\n"
        "[\n"
        "  {\n"
        '    "severity": "High" | "Medium" | "Low" | "Info",\n'
        '    "file": "path/to/file",\n'
        '    "title": "Concise title of vulnerability",\n'
        '    "evidence_span": "Line number reference or sanitized code location (no secrets printed)",\n'
        '    "recommendation": "Safe remediation advice"\n'
        "  }\n"
        "]\n"
        "Return ONLY valid JSON. If no issues found, return []."
    ),
    "missing_tests": (
        "Pass 3: Test Coverage & Regression Auditor\n"
        "Analyze the provided repository files and identify changed or core functions/classes that lack "
        "corresponding unit or integration tests in the repository test suite.\n\n"
        "Return a JSON array of findings with this exact schema:\n"
        "[\n"
        "  {\n"
        '    "severity": "High" | "Medium" | "Low" | "Info",\n'
        '    "file": "path/to/untested/file",\n'
        '    "title": "Missing tests for <function_or_class>",\n'
        '    "evidence_span": "Function signature or definition lacking tests",\n'
        '    "recommendation": "Suggested test cases to add"\n'
        "  }\n"
        "]\n"
        "Return ONLY valid JSON. If no issues found, return []."
    ),
}


def _format_context_for_prompt(pack_result: PackResult) -> str:
    """Formats packed files into structured text for prompt context."""
    chunks = [
        f"# Repository: {pack_result.repo_path.name}",
        f"# Target ref / glob: {pack_result.ref_or_glob}",
        f"# Total files included: {pack_result.total_files}\n",
    ]

    for f in pack_result.files:
        status_tag = []
        if f.is_diff_match:
            status_tag.append("CHANGED")
        if f.is_ast_import:
            status_tag.append(f"ONE-HOP-IMPORT(from {f.imported_by})")
        tag_str = f" [{', '.join(status_tag)}]" if status_tag else ""

        chunks.append(f"--- FILE: {f.rel_path}{tag_str} ---")
        chunks.append(f.content)
        chunks.append(f"--- END FILE: {f.rel_path} ---\n")

    return "\n".join(chunks)


def parse_findings_json(raw_text: str) -> List[Dict[str, Any]]:
    """Extracts and parses JSON list from model output safely."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            valid_findings = []
            for item in data:
                if isinstance(item, dict):
                    valid_findings.append({
                        "severity": str(item.get("severity", "Medium")),
                        "file": str(item.get("file", "")),
                        "title": str(item.get("title", "Untitled finding")),
                        "evidence_span": str(item.get("evidence_span", "")),
                        "recommendation": str(item.get("recommendation", "")),
                    })
            return valid_findings
    except Exception:
        match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if match:
            try:
                sub_data = json.loads(match.group(0))
                if isinstance(sub_data, list):
                    return [
                        {
                            "severity": str(item.get("severity", "Medium")),
                            "file": str(item.get("file", "")),
                            "title": str(item.get("title", "Untitled finding")),
                            "evidence_span": str(item.get("evidence_span", "")),
                            "recommendation": str(item.get("recommendation", "")),
                        }
                        for item in sub_data if isinstance(item, dict)
                    ]
            except Exception:
                pass

    return []


def run_llm_pass(
    client: OpenAI,
    model: str,
    pass_name: str,
    pack_result: PackResult,
) -> List[Dict[str, Any]]:
    """Executes a single focused audit pass against Agnes AI / OpenAI."""
    instructions = PASS_INSTRUCTIONS.get(pass_name)
    if not instructions:
        return []

    context_text = _format_context_for_prompt(pack_result)

    messages = [
        {"role": "system", "content": instructions},
        {
            "role": "user",
            "content": f"Please audit the following repository files according to your instructions:\n\n{context_text}",
        },
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,
    )

    content = response.choices[0].message.content or "[]"
    return parse_findings_json(content)


def run_three_pass_audit(
    pack_result: PackResult,
    provider_name: str = "Agnes AI",
    model_name: str = "agnes-3.0-flash",
    progress_callback: Optional[Callable[[str, int], None]] = None,
    cache_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Runs all 3 separate passes sequentially and saves merged findings to data/cache/last_audit.json."""
    client = create_openai_client(provider_name)
    if not client:
        raise RuntimeError(f"Unable to initialize client for provider: {provider_name}. Check API key.")

    all_findings: List[Dict[str, Any]] = []
    pass_summaries: Dict[str, int] = {}

    passes = [
        ("breaking_api", "Pass 1/3: Breaking API & call-site drift"),
        ("security", "Pass 2/3: Security & injection checks (locations only)"),
        ("missing_tests", "Pass 3/3: Missing test coverage"),
    ]

    for idx, (pass_key, pass_label) in enumerate(passes, start=1):
        if progress_callback:
            progress_callback(pass_label, int((idx / len(passes)) * 100))

        findings = run_llm_pass(client, model_name, pass_key, pack_result)
        for f in findings:
            f["pass"] = pass_key
        all_findings.extend(findings)
        pass_summaries[pass_key] = len(findings)

    # Save to data/cache/last_audit.json
    target_cache = cache_path or Path("data/cache/last_audit.json")
    target_cache.parent.mkdir(parents=True, exist_ok=True)

    result_payload = {
        "repository": pack_result.repo_path.name,
        "repo_path": str(pack_result.repo_path),
        "ref_or_glob": pack_result.ref_or_glob,
        "total_files": pack_result.total_files,
        "total_chars": pack_result.total_chars,
        "provider": provider_name,
        "model": model_name,
        "pass_summaries": pass_summaries,
        "findings": all_findings,
    }

    target_cache.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
    return result_payload


# Static audit checks for deterministic pre-flight screening
SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID pattern", "High"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub Personal Access Token pattern", "High"),
    (r"gho_[A-Za-z0-9]{36}", "GitHub OAuth Access Token pattern", "High"),
    (r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private Key Header", "High"),
    (r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]", "Hardcoded API Key assignment", "High"),
    (r"(?i)password\s*[:=]\s*['\"][^'\"]{6,}['\"]", "Hardcoded password pattern", "High"),
    (r"(?i)bearer\s+[A-Za-z0-9_\-\.]{20,}", "Hardcoded Bearer token", "High"),
]


@dataclass
class Finding:
    category: str
    severity: str
    title: str
    description: str
    file_path: str = ""
    line_number: int = 0
    snippet: str = ""


@dataclass
class AuditReport:
    repo_name: str
    total_files_audited: int
    findings: List[Finding] = field(default_factory=list)


def run_static_audit(pack_result: PackResult) -> AuditReport:
    """Lightweight regex static scanner."""
    findings: List[Finding] = []
    for f in pack_result.files:
        for idx, line in enumerate(f.content.splitlines(), start=1):
            for pattern, title, sev in SECRET_PATTERNS:
                if re.search(pattern, line):
                    findings.append(
                        Finding(
                            category="Security",
                            severity=sev,
                            title=title,
                            description=f"Potential credential pattern detected at line {idx}",
                            file_path=f.rel_path,
                            line_number=idx,
                            snippet="[REDACTED]",
                        )
                    )
    return AuditReport(
        repo_name=pack_result.repo_path.name,
        total_files_audited=pack_result.total_files,
        findings=findings,
    )

