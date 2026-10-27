
import re
from io import BytesIO
from xml.sax.saxutils import escape

from flask import Blueprint, abort, render_template, send_file
from flask_login import login_required
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app import db
from app.audit import record
from app.models import Inspection, utcnow

reports_bp = Blueprint("reports", __name__)

TYPE_LABELS = {
    "general": "General",
    "safety": "Safety",
    "quality": "Quality",
    "environmental": "Environmental",
}

STATUS_LABELS = {
    "draft": "Draft",
    "in_progress": "In progress",
    "completed": "Completed",
    "cancelled": "Cancelled",
}

RESULT_LABELS = {
    "pass": "Pass",
    "fail": "Fail",
    "not_applicable": "Not applicable",
    "not_inspected": "Not inspected",
}

SEVERITY_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "critical": "Critical",
}

FINDING_STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "resolved": "Resolved",
    "closed": "Closed",
}

ACTION_STATUS_LABELS = {
    "open": "Open",
    "in_progress": "In progress",
    "completed": "Completed",
}

NAVY = colors.HexColor("#0f2c4c")
LINE = colors.HexColor("#9aa5ad")
HEAD = colors.HexColor("#e8eef2")


def file_names(rows):
    return [
        row.original_name
        for row in sorted(rows, key=lambda row: row.id)
    ]


def load_report(inspection_id):
    inspection = db.session.get(Inspection, inspection_id)

    if inspection is None:
        abort(404)

    items = sorted(
        inspection.checklist_items,
        key=lambda item: (item.sort_order, item.id),
    )

    counts = {key: 0 for key in RESULT_LABELS}

    for item in items:
        if item.result in counts:
            counts[item.result] += 1

    findings = []

    for finding in inspection.findings:
        actions = []

        for action in finding.corrective_actions:
            actions.append({
                "record": action,
                "files": file_names(action.attachments),
            })

        findings.append({
            "record": finding,
            "files": file_names(finding.attachments),
            "actions": actions,
        })

    return {
        "inspection": inspection,
        "items": items,
        "counts": counts,
        "findings": findings,
        "inspection_files": file_names(inspection.attachments),
        "generated_at": utcnow(),
        "type_labels": TYPE_LABELS,
        "status_labels": STATUS_LABELS,
        "result_labels": RESULT_LABELS,
        "severity_labels": SEVERITY_LABELS,
        "finding_status_labels": FINDING_STATUS_LABELS,
        "action_status_labels": ACTION_STATUS_LABELS,
    }


def show_date(value):
    if value is None:
        return "Not recorded"
    return value.strftime("%d %b %Y")


def show_time(value):
    if value is None:
        return "Not recorded"
    return value.strftime("%d %b %Y %H:%M UTC")


def pdf_name(inspection_number):
    safe = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        inspection_number or "",
    ).strip("-")

    if not safe:
        safe = "inspection"

    return f"{safe[:40]}-report.pdf"


def text_cell(value, style):
    cleaned = escape(str(value or "")).replace("\n", "<br/>")
    return Paragraph(cleaned or "—", style)


def table(rows, widths):
    grid = Table(rows, colWidths=widths, repeatRows=1)

    grid.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), HEAD),
            ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])
    )

    return grid


def build_pdf(data):
    inspection = data["inspection"]
    styles = getSampleStyleSheet()

    body = ParagraphStyle(
        "SeedBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.black,
    )

    small = ParagraphStyle(
        "SeedSmall",
        parent=body,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#333333"),
    )

    title = ParagraphStyle(
        "SeedTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=NAVY,
        spaceAfter=2,
    )

    heading = ParagraphStyle(
        "SeedHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=NAVY,
        spaceBefore=8,
        spaceAfter=4,
    )

    story = [
        Paragraph("SEED Inspect", title),
        Paragraph("Inspection report", heading),
        Paragraph(
            "Academic prototype. This PDF is built from records "
            "already saved. It is not a company approval.",
            small,
        ),
        Spacer(1, 4 * mm),
        Paragraph(
            escape(f"{inspection.inspection_number} — {inspection.title}"),
            heading,
        ),
    ]

    facts = [
        ["Project", f"{inspection.project.code} — {inspection.project.name}"],
        ["Site", f"{inspection.site.code} — {inspection.site.name}"],
        [
            "Type",
            data["type_labels"].get(
                inspection.inspection_type,
                inspection.inspection_type,
            ),
        ],
        [
            "Status",
            data["status_labels"].get(inspection.status, inspection.status),
        ],
        ["Scheduled date", show_date(inspection.scheduled_date)],
        [
            "Inspector",
            inspection.inspector.full_name
            if inspection.inspector
            else "Not assigned",
        ],
        ["Started", show_time(inspection.started_at)],
        ["Completed", show_time(inspection.completed_at)],
        ["Summary", inspection.summary or "Not recorded"],
    ]

    fact_rows = [
        [text_cell(left, body), text_cell(right, body)]
        for left, right in facts
    ]

    story.append(table(fact_rows, [40 * mm, 140 * mm]))
    story.append(Paragraph("Checklist", heading))

    counts = data["counts"]

    story.append(
        Paragraph(
            f"Pass {counts['pass']}. Fail {counts['fail']}. "
            f"Not applicable {counts['not_applicable']}. "
            f"Not inspected {counts['not_inspected']}.",
            body,
        )
    )

    if data["items"]:
        header = [
            text_cell(label, body)
            for label in ("Order", "Line", "Result", "Notes")
        ]

        rows = [header]

        for item in data["items"]:
            rows.append([
                text_cell(str(item.sort_order), body),
                text_cell(item.item_text, body),
                text_cell(
                    data["result_labels"].get(item.result, item.result),
                    body,
                ),
                text_cell(item.notes or "—", body),
            ])

        story.append(Spacer(1, 2 * mm))
        story.append(
            table(rows, [18 * mm, 78 * mm, 32 * mm, 52 * mm])
        )
    else:
        story.append(Paragraph("No checklist lines.", body))

    story.append(
        Paragraph(
            "A Fail line is a checklist result. "
            "It does not create a finding by itself.",
            small,
        )
    )

    story.append(Paragraph("Findings and corrective actions", heading))

    if data["findings"]:
        for item in data["findings"]:
            finding = item["record"]

            story.append(Paragraph(escape(finding.title), heading))

            story.append(
                Paragraph(
                    "Severity: "
                    + escape(
                        data["severity_labels"].get(
                            finding.severity,
                            finding.severity,
                        )
                    )
                    + ". Status: "
                    + escape(
                        data["finding_status_labels"].get(
                            finding.status,
                            finding.status,
                        )
                    )
                    + ".",
                    body,
                )
            )

            story.append(
                Paragraph(
                    escape(finding.description or "").replace("\n", "<br/>"),
                    body,
                )
            )

            story.append(
                Paragraph(
                    "Evidence note: "
                    + escape(finding.evidence_note or "Not recorded"),
                    body,
                )
            )

            story.append(
                Paragraph(
                    "Files on this finding: "
                    + escape(
                        ", ".join(item["files"])
                        if item["files"]
                        else "None"
                    ),
                    body,
                )
            )

            if item["actions"]:
                header = [
                    text_cell(label, body)
                    for label in (
                        "Action",
                        "Responsible person",
                        "Due",
                        "Status",
                        "Files",
                    )
                ]

                rows = [header]

                for action_item in item["actions"]:
                    action = action_item["record"]

                    rows.append([
                        text_cell(action.action_text, body),
                        text_cell(action.responsible_name, body),
                        text_cell(show_date(action.due_date), body),
                        text_cell(
                            data["action_status_labels"].get(
                                action.status,
                                action.status,
                            ),
                            body,
                        ),
                        text_cell(
                            ", ".join(action_item["files"])
                            if action_item["files"]
                            else "None",
                            body,
                        ),
                    ])

                story.append(Spacer(1, 2 * mm))
                story.append(
                    table(rows, [52 * mm, 35 * mm, 28 * mm, 25 * mm, 40 * mm])
                )
            else:
                story.append(
                    Paragraph("No corrective actions for this finding.", body)
                )
    else:
        story.append(
            Paragraph(
                "No findings have been recorded for this inspection.",
                body,
            )
        )

    story.append(Paragraph("Files on this inspection", heading))

    if data["inspection_files"]:
        for name in data["inspection_files"]:
            story.append(Paragraph("• " + escape(name), body))
    else:
        story.append(Paragraph("None.", body))

    story.append(
        Paragraph(
            "This report lists file names. It does not place the picture "
            "or PDF attachment inside this file.",
            small,
        )
    )

    story.append(Spacer(1, 3 * mm))

    story.append(
        Paragraph(
            "Generated "
            + escape(data["generated_at"].strftime("%d %b %Y %H:%M UTC"))
            + ".",
            small,
        )
    )

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=16 * mm,
        title=f"{inspection.inspection_number} inspection report",
        author="SEED Inspect",
    )

    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    buffer.seek(0)

    return buffer


def draw_footer(canvas, document):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#333333"))
    canvas.drawString(15 * mm, 8 * mm, "SEED Inspect academic prototype")
    canvas.drawRightString(
        A4[0] - 15 * mm,
        8 * mm,
        f"Page {document.page}",
    )
    canvas.restoreState()


@reports_bp.route("/inspections/<int:inspection_id>/report")
@login_required
def inspection_report(inspection_id):
    return render_template(
        "inspection_report.html",
        **load_report(inspection_id),
    )


@reports_bp.route("/inspections/<int:inspection_id>/report.pdf")
@login_required
def inspection_pdf(inspection_id):
    data = load_report(inspection_id)
    inspection = data["inspection"]

    record(
        "download",
        "report",
        f"Downloaded the PDF report for {inspection.inspection_number}.",
        inspection.id,
    )
    db.session.commit()

    return send_file(
        build_pdf(data),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=pdf_name(inspection.inspection_number),
    )
