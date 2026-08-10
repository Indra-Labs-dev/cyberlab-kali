from jinja2 import Template

# autoescape=True is required: finding titles/descriptions/evidence can
# contain content reflecting the scanned target (tool output), e.g. a nikto
# finding echoing a page's raw <script> tag. Without escaping, a malicious
# or compromised scan target could inject script into the HTML report that
# executes when someone opens it in a browser.
_SEVERITY_COLORS = {
    "INFO": "#64748b",
    "LOW": "#0891b2",
    "MEDIUM": "#d97706",
    "HIGH": "#ea580c",
    "CRITICAL": "#dc2626",
}

_TEMPLATE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ data.title }}</title>
<style>
  body { font-family: -apple-system, Segoe UI, Helvetica, Arial, sans-serif; max-width: 860px;
         margin: 2rem auto; padding: 0 1rem; color: #1e293b; line-height: 1.5; }
  h1 { margin-bottom: 0.2rem; }
  .meta { color: #64748b; font-size: 0.85rem; margin-bottom: 2rem; }
  h2 { margin-top: 2.5rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.3rem; }
  .summary-grid { display: flex; gap: 1.5rem; margin: 1rem 0; }
  .summary-tile { border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.75rem 1rem; }
  .summary-tile .value { font-size: 1.4rem; font-weight: 600; }
  .finding { border: 1px solid #e2e8f0; border-radius: 8px; padding: 1rem; margin-bottom: 0.75rem; }
  .badge { display: inline-block; color: white; border-radius: 4px; padding: 0.1rem 0.5rem;
           font-size: 0.75rem; font-weight: 600; }
  .finding-meta { color: #64748b; font-size: 0.8rem; margin: 0.3rem 0; }
  .recommendation { background: #f0fdf4; border-left: 3px solid #22c55e; padding: 0.5rem 0.75rem;
                     margin-top: 0.5rem; font-size: 0.9rem; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e2e8f0; font-size: 0.85rem; }
  code { background: #f1f5f9; padding: 0.1rem 0.3rem; border-radius: 3px; }
</style>
</head>
<body>
  <h1>{{ data.title }}</h1>
  <p class="meta">Generated {{ data.generated_at }} — CyberLab</p>

  <h2>Executive Summary</h2>
  <div class="summary-grid">
    <div class="summary-tile"><div class="value">{{ data.executive_summary.total_jobs }}</div>Jobs analyzed</div>
    <div class="summary-tile"><div class="value">{{ data.executive_summary.total_findings }}</div>Findings</div>
  </div>
  {% if data.executive_summary.by_severity %}
  <table>
    <tr>{% for sev, count in data.executive_summary.by_severity.items() %}<th>{{ sev }}</th>{% endfor %}</tr>
    <tr>{% for sev, count in data.executive_summary.by_severity.items() %}<td>{{ count }}</td>{% endfor %}</tr>
  </table>
  {% endif %}

  <h2>Scope</h2>
  <p><strong>Targets:</strong> {{ data.scope.targets | join(", ") }}</p>
  <p><strong>Tools used:</strong> {{ data.scope.tools_used | join(", ") }}</p>

  <h2>Findings</h2>
  {% if not data.findings %}<p>No findings extracted.</p>{% endif %}
  {% for f in data.findings %}
  <div class="finding">
    <span class="badge" style="background:{{ colors.get(f.severity, '#64748b') }}">{{ f.severity }}</span>
    <strong>{{ f.title }}</strong>
    <div class="finding-meta">Target: <code>{{ f.target }}</code> · Source: {{ f.source_tool }} · Confidence: {{ f.confidence }}</div>
    <p>{{ f.description }}</p>
    {% if f.recommendation %}<div class="recommendation">{{ f.recommendation }}</div>{% endif %}
  </div>
  {% endfor %}

  <h2>Timeline &amp; AI Analysis</h2>
  {% for job in data.jobs %}
  <div class="finding">
    <strong>{{ job.tool }} → {{ job.target }}</strong> ({{ job.status }})
    <div class="finding-meta">Created: {{ job.created_at }} · Started: {{ job.started_at }} · Finished: {{ job.finished_at }}</div>
    {% if job.ai_analysis %}
    <p><strong>AI risk assessment: {{ job.ai_analysis.risk }}</strong> — {{ job.ai_analysis.summary }}</p>
    {% endif %}
  </div>
  {% endfor %}
</body>
</html>
""",
    autoescape=True,
)


def render(data: dict) -> str:
    return _TEMPLATE.render(data=data, colors=_SEVERITY_COLORS)
