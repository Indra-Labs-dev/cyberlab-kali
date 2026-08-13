def render(data: dict, template: str = "technical") -> str:
    lines = [f"# {data['title']}", "", f"_Generated {data['generated_at']}_", ""]

    lines += ["## Executive Summary", ""]
    summary = data["executive_summary"]
    lines.append(f"- Jobs analyzed: {summary['total_jobs']}")
    lines.append(f"- Findings: {summary['total_findings']}")
    if summary["by_severity"]:
        breakdown = ", ".join(f"{sev}: {count}" for sev, count in summary["by_severity"].items())
        lines.append(f"- By severity: {breakdown}")
    lines.append("")

    lines += ["## Scope", ""]
    lines.append("**Targets:** " + ", ".join(data["scope"]["targets"]))
    lines.append("**Tools used:** " + ", ".join(data["scope"]["tools_used"]))
    lines.append("")

    lines += ["## Findings", ""]
    if not data["findings"]:
        lines.append("_No findings extracted._")
    for f in data["findings"]:
        lines.append(f"### [{f['severity']}] {f['title']}")
        lines.append("")
        lines.append(f"- **Target:** {f['target']}")
        lines.append(f"- **Source:** {f['source_tool']}")
        lines.append(f"- **Confidence:** {f['confidence']}")
        lines.append("")
        if template != "executive":
            lines.append(f["description"])
            if f["recommendation"]:
                lines.append("")
                lines.append(f"**Recommendation:** {f['recommendation']}")
            lines.append("")
        if template == "evidence_package" and f["evidence"]:
            lines.append("**Evidence:**")
            lines.append("")
            lines.append(f"```\n{f['evidence']}\n```")
            lines.append("")
    lines.append("")

    if template != "executive":
        lines += ["## Timeline & AI Analysis", ""]
        for job in data["jobs"]:
            lines.append(f"### {job['tool']} → {job['target']} ({job['status']})")
            lines.append(f"- Created: {job['created_at']}")
            lines.append(f"- Started: {job['started_at']}")
            lines.append(f"- Finished: {job['finished_at']}")
            if template == "evidence_package":
                lines.append(f"- Evidence SHA-256: `{job['evidence_sha256'] or '—'}`")
            if job["ai_analysis"]:
                ai = job["ai_analysis"]
                lines.append(f"- AI risk assessment: **{ai.get('risk', 'N/A')}** — {ai.get('summary', '')}")
            lines.append("")

    return "\n".join(lines)
