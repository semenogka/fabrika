from __future__ import annotations

import os
import re
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


PROJECT_TITLE = "Фабрика гипотез"
TOTAL_HYPOTHESES = 5
FONT_CANDIDATES = (
    ("ArialUnicode", "C:/Windows/Fonts/arial.ttf"),
    ("CalibriUnicode", "C:/Windows/Fonts/calibri.ttf"),
    ("TahomaUnicode", "C:/Windows/Fonts/tahoma.ttf"),
    ("VerdanaUnicode", "C:/Windows/Fonts/verdana.ttf"),
    ("TimesUnicode", "C:/Windows/Fonts/times.ttf"),
)
HYPOTHESIS_FIELDS = (
    ("description", "Описание"),
    ("mechanism", "Механизм"),
    ("reason", "Почему появилась"),
    ("expected_effect", "Ожидаемый эффект"),
    ("novelty", "Новизна"),
    ("required_resources", "Ресурсы"),
    ("verification_plan", "План проверки"),
    ("evidence", "Источники"),
    ("confidence", "Уверенность"),
    ("priority", "Приоритет"),
)


def _stringify_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, Mapping):
        parts = []
        for key, item in value.items():
            rendered = _stringify_value(item)
            if rendered:
                parts.append(f"{key}: {rendered}")
        return ", ".join(parts).strip()
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return ", ".join(part for part in (_stringify_value(item) for item in value) if part).strip()
    return str(value).strip()


def _escape(text: Any) -> str:
    value = _stringify_value(text)
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _clean_hypothesis_title(title: Any, index: int) -> str:
    cleaned = _stringify_value(title)
    if not cleaned:
        return "не указано"

    cleaned = re.sub(
        rf"^\s*гипотеза\s*{index}\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(
        r"^\s*гипотеза\s*\d+\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    prefix, separator, remainder = cleaned.partition(":")
    if separator and remainder.strip() and str(index) in prefix:
        cleaned = remainder.strip()

    return cleaned or "не указано"


def _register_font() -> str:
    for font_name, font_path in FONT_CANDIDATES:
        if Path(font_path).exists():
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                return font_name
            except Exception:
                continue
    raise RuntimeError("Не найден системный шрифт с поддержкой кириллицы для PDF-экспорта.")


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#1F2937"),
            spaceAfter=8,
        ),
        "meta": ParagraphStyle(
            "ReportMeta",
            parent=styles["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#4B5563"),
            spaceAfter=6,
        ),
        "section": ParagraphStyle(
            "SectionTitle",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#111827"),
            spaceBefore=8,
            spaceAfter=8,
        ),
        "subsection": ParagraphStyle(
            "SubsectionTitle",
            parent=styles["Heading3"],
            fontName=font_name,
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#1F2937"),
            spaceBefore=6,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "BodyText",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            alignment=TA_LEFT,
            spaceAfter=6,
        ),
        "label": ParagraphStyle(
            "LabelText",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#111827"),
            spaceAfter=4,
        ),
    }


def _paragraph(text: Any, style: ParagraphStyle, prefix: str = "") -> Paragraph:
    return Paragraph(f"{prefix}{_escape(text) or 'не указано'}", style)


def _append_text_block(story: list[Any], title: str, content: Any, styles: dict[str, ParagraphStyle]) -> None:
    rendered = _stringify_value(content)
    if not rendered:
        return
    story.append(Paragraph(_escape(title), styles["subsection"]))
    story.append(_paragraph(rendered, styles["body"]))


def _append_list_block(
    story: list[Any],
    title: str,
    items: Any,
    styles: dict[str, ParagraphStyle],
    bullet_type: str = "bullet",
) -> None:
    story.append(Paragraph(_escape(title), styles["subsection"]))
    normalized_items = []
    if isinstance(items, Iterable) and not isinstance(items, (str, bytes, Mapping)):
        for item in items:
            if isinstance(item, Mapping):
                normalized = _stringify_value(item)
            else:
                normalized = _stringify_value(item)
            if normalized:
                normalized_items.append(normalized)
    else:
        rendered = _stringify_value(items)
        if rendered:
            normalized_items.append(rendered)

    if not normalized_items:
        story.append(_paragraph("не указано", styles["body"]))
        return

    flowable = ListFlowable(
        [
            ListItem(Paragraph(_escape(item), styles["body"]))
            for item in normalized_items
        ],
        bulletType="1" if bullet_type == "numbered" else "bullet",
        leftIndent=14,
    )
    story.append(flowable)
    story.append(Spacer(1, 4))


def _append_file_statuses(story: list[Any], file_statuses: Any, styles: dict[str, ParagraphStyle]) -> None:
    if not file_statuses:
        return

    story.append(Paragraph("Загруженные файлы", styles["section"]))
    table_rows = [["Файл", "Расширение", "Статус", "Сообщение", "Объём текста"]]
    for item in file_statuses:
        if not isinstance(item, Mapping):
            continue
        table_rows.append(
            [
                _escape(item.get("name")),
                _escape(item.get("extension")),
                _escape(item.get("status_label") or item.get("status")),
                _escape(item.get("message") or "—"),
                _escape(item.get("text_length") or 0),
            ]
        )

    table = Table(
        table_rows,
        colWidths=[52 * mm, 22 * mm, 33 * mm, 55 * mm, 20 * mm],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")),
                ("FONTNAME", (0, 0), (-1, -1), styles["body"].fontName),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEADING", (0, 0), (-1, -1), 11),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 10))


def _append_hypotheses(story: list[Any], hypotheses: list[Any], styles: dict[str, ParagraphStyle]) -> None:
    if not hypotheses:
        return

    story.append(Paragraph("Гипотезы", styles["section"]))
    for index, hypothesis in enumerate(hypotheses, start=1):
        if not isinstance(hypothesis, Mapping):
            hypothesis = {"raw_response": _stringify_value(hypothesis)}

        story.append(
            Paragraph(
                _escape(f"Гипотеза {index}: {_clean_hypothesis_title(hypothesis.get('title'), index)}"),
                styles["subsection"],
            )
        )

        for field_name, label in HYPOTHESIS_FIELDS:
            value = hypothesis.get(field_name)
            if field_name == "required_resources":
                _append_list_block(story, label, value or [], styles, bullet_type="bullet")
                continue
            if field_name == "verification_plan":
                _append_list_block(story, label, value or [], styles, bullet_type="numbered")
                continue
            if field_name == "evidence":
                evidence_items = []
                if isinstance(value, Iterable) and not isinstance(value, (str, bytes, Mapping)):
                    for item in value:
                        if isinstance(item, Mapping):
                            source = _stringify_value(item.get("source")) or "источник не указан"
                            page = _stringify_value(item.get("page"))
                            reason = _stringify_value(item.get("reason"))
                            parts = [source]
                            if page:
                                parts.append(f"page {page}")
                            if reason:
                                parts.append(reason)
                            evidence_items.append(", ".join(parts))
                        else:
                            rendered = _stringify_value(item)
                            if rendered:
                                evidence_items.append(rendered)
                else:
                    rendered = _stringify_value(value)
                    if rendered:
                        evidence_items.append(rendered)
                _append_list_block(story, label, evidence_items, styles, bullet_type="bullet")
                continue

            story.append(_paragraph(value, styles["body"], prefix=f"<b>{_escape(label)}:</b> "))

        raw_response = _stringify_value(hypothesis.get("raw_response"))
        if raw_response:
            story.append(_paragraph(raw_response, styles["body"], prefix="<b>Текст модели:</b> "))

        if index < len(hypotheses):
            story.append(Spacer(1, 8))


def _page_canvas(canvas, doc, title: str) -> None:
    canvas.saveState()
    canvas.setFont(doc.report_font_name, 9)
    canvas.setFillColor(colors.HexColor("#6B7280"))
    canvas.drawString(doc.leftMargin, 10 * mm, title)
    canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, str(canvas.getPageNumber()))
    canvas.restoreState()


def _resolve_generation_datetime(state: Mapping[str, Any]) -> str:
    for key in ("generation_completed_at", "generated_at"):
        value = _stringify_value(state.get(key))
        if value:
            return value
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def should_enable_pdf_download(state: Mapping[str, Any]) -> bool:
    final_report = _stringify_value(state.get("final_report"))
    hypotheses = state.get("progressive_hypotheses") or []
    return bool(final_report or len(hypotheses) == TOTAL_HYPOTHESES)


def build_report_pdf(state: Mapping[str, Any], kpi_problem: str, constraints: str) -> bytes:
    font_name = _register_font()
    styles = _build_styles(font_name)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=PROJECT_TITLE,
        author=PROJECT_TITLE,
    )
    doc.report_font_name = font_name

    story: list[Any] = [
        Paragraph(_escape(PROJECT_TITLE), styles["title"]),
        _paragraph(f"Дата и время генерации: {_resolve_generation_datetime(state)}", styles["meta"]),
        Spacer(1, 6),
        Paragraph("Контекст", styles["section"]),
        _paragraph(kpi_problem or "не указано", styles["body"], prefix="<b>KPI / технологическая проблема:</b> "),
        _paragraph(constraints or "не указано", styles["body"], prefix="<b>Ограничения:</b> "),
        Spacer(1, 4),
    ]

    _append_file_statuses(story, state.get("file_statuses"), styles)

    hypotheses = state.get("progressive_hypotheses") or []
    if hypotheses:
        _append_hypotheses(story, list(hypotheses), styles)

    critique = _stringify_value(state.get("critique"))
    if critique:
        story.append(PageBreak())
        story.append(Paragraph("Review / критика", styles["section"]))
        story.append(_paragraph(critique, styles["body"]))

    final_report = _stringify_value(state.get("final_report"))
    if final_report:
        story.append(PageBreak())
        story.append(Paragraph("Итоговый отчёт", styles["section"]))
        story.append(_paragraph(final_report, styles["body"]))

    doc.build(
        story,
        onFirstPage=lambda canvas, page_doc: _page_canvas(canvas, page_doc, PROJECT_TITLE),
        onLaterPages=lambda canvas, page_doc: _page_canvas(canvas, page_doc, PROJECT_TITLE),
    )
    return buffer.getvalue()
