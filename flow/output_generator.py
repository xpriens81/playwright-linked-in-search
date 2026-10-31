import json
import re
from datetime import datetime, timezone
from pathlib import Path

from common.logger import setup_logger

logger = setup_logger(__name__)
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output"

def text_block(text):
    fence = "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", text)), default=0))
    return f"{fence}text\n{text}\n{fence}\n\n"

def generate_markdown(questions, title):
    report = getattr(questions, "report", {})
    markdown = f"# {title}\n\n"
    markdown += f"Latest search: {report.get('search_term', title)}\n\n"
    markdown += f"Generated: {report.get('generated_at', datetime.now(timezone.utc).isoformat())}\n\n"
    markdown += f"Status: **{report.get('status', 'complete')}**\n\n"
    for warning in report.get("warnings", []):
        markdown += f"- {warning}\n"
    if report.get("warnings"):
        markdown += f"\n"
    for post in report.get("posts", []):
        for document in post.get("documents", []):
            markdown += (
                f"- Document `{document['document_id']}`: "
                f"{document.get('captured_pages', 0)}/{document.get('expected_pages', 0)} pages captured; "
                f"text {'complete' if document.get('text_complete') else 'incomplete'}; "
                f"stop: {document.get('stop_reason', 'unknown')}.\n"
            )
            if document.get("missing_pages"):
                markdown += f"  Missing pages: {document.get('missing_pages')}.\n"
    markdown += "\n"
    if not questions:
        markdown += f"No interview questions could be extracted. See the JSON report for raw text and failures. \n"
        return markdown
    for index, question in enumerate(questions):
        markdown += f"## Q{index}\n\n" + text_block(question.get("question", ''))
        answer = question.get('answer', '').strip()
        markdown += "**Answer:**\n\n" + text_block(answer) if answer else "*No answer provided*\n\n"
        if question.get("needs_review"):
            markdown += "**Review required: ** OCR/alt text or a heuristic question boundary was used.\n\n"
        for source in question.get("sources", []):
            location = source.get("post_url") or f"LinkedIn Post {source.get('post_id', 'unknown')}"
            markdown += f"Source: {location}; document: `{source.get('document_id', 'post text')}`; "
            markdown += f"pages {source.get('page_start', 1)}-{source.get('page_end', 1)}.\n\n"
        if not question.get("sources"):
            markdown += f"Source: {question.get('source', 'LinkedIn')}\n\n"

    return markdown

def overwrite(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)

def save_markdown(questions, filename, title):
    try:
        path = OUTPUT_DIR / Path(filename).name
        report = dict(getattr(questions, "report", {}))
        report["questions"] = list(questions)
        overwrite(path.with_suffix(".json"), json.dumps(report, ensure_ascii=False, indent=4))
        overwrite(path, generate_markdown(questions, title))
        logger.info(f"Overwrite %s with %s questions", path, len(questions))
        return True
    except Exception as e:
        logger.error(f"Failed to save {filename}: {e}")
        return False

def generate_all_outputs(question_list, query_file, query_description):
    success = save_markdown(question_list, query_file, query_description)
    return success
