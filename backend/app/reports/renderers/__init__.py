from app.reports.renderers import html_renderer, json_renderer, markdown_renderer, pdf_renderer

TEXT_RENDERERS = {
    "json": json_renderer.render,
    "markdown": markdown_renderer.render,
    "html": html_renderer.render,
}

BINARY_RENDERERS = {
    "pdf": pdf_renderer.render,
}


def render(report_format: str, data: dict) -> tuple[str, bool]:
    """Returns (content, is_binary). Binary content (pdf) is base64-encoded
    by the caller before persisting to the Report.content text column.
    """
    if report_format in TEXT_RENDERERS:
        return TEXT_RENDERERS[report_format](data), False
    if report_format in BINARY_RENDERERS:
        import base64

        raw = BINARY_RENDERERS[report_format](data)
        return base64.b64encode(raw).decode("ascii"), True
    raise ValueError(f"unknown report format: {report_format}")
