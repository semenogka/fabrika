import json
import os
import re
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

import streamlit as st

from pipeline import (
    analyze_articles,
    analyze_kpi,
    explain,
    find_patterns,
    generate_hypothesis,
    generate_single_hypothesis,
    review,
)
from reader import read_file
from report_export import build_report_pdf, should_enable_pdf_download


SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls"}
TOTAL_HYPOTHESES = 5
DEFAULT_DEBUG = os.getenv("STREAMLIT_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
SESSION_DEFAULTS = {
    "debug_enabled": DEFAULT_DEBUG,
    "structured_kpi": "",
    "literature_analysis": "",
    "patterns": "",
    "hypotheses": "",
    "critique": "",
    "final_report": "",
    "file_statuses": [],
    "stage_outputs_preview": {},
    "errors": "",
    "traceback": "",
    "completed_stages": [],
    "debug_prompt": "",
    "debug_constraints": "",
    "debug_file_list": [],
    "debug_file_text_lengths": {},
    "debug_file_errors": {},
    "literature_context_length": 0,
    "debug_literature_context_preview": "",
    "progressive_hypotheses": [],
    "completed_hypothesis_count": 0,
    "current_hypothesis_index": 0,
    "progressive_generation_error": "",
    "debug_previous_hypotheses": [],
    "kpi_problem_text": "",
    "constraints_text": "",
    "generation_completed_at": "",
    "is_generating": False,
    "generation_requested": False,
}


def split_hypotheses(text):
    parts = re.split(r"(?=Гипотеза\s+\d+:)", text)
    return [p.strip() for p in parts if p.strip()]


def render_hypotheses(text: str):
    # Делим текст по заголовкам "Гипотеза N"
    parts = re.split(r"(?=\*\*Гипотеза\s+\d+:)", text)

    for part in parts:
        part = part.strip()
        if not part:
            continue

        first_line = part.split("\n", 1)[0]
        title = re.sub(r"\*\*", "", first_line)

        with st.expander(title, expanded=False):
            st.markdown(part)


def _stringify_value(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return ", ".join(
            f"{key}: {item}"
            for key, item in value.items()
            if item not in (None, "", [], {})
        ).strip()
    if isinstance(value, list):
        return ", ".join(
            part for part in (_stringify_value(item) for item in value) if part
        ).strip()
    return str(value).strip()


def _render_bullet_list(items):
    if not items:
        st.markdown("- не указано")
        return
    for item in items:
        text = _stringify_value(item)
        if text:
            st.markdown(f"- {text}")


def _render_numbered_list(items):
    if not items:
        st.markdown("1. не указано")
        return
    for item in items:
        text = _stringify_value(item)
        if text:
            st.markdown(f"1. {text}")


def _render_evidence_list(evidence):
    if not evidence:
        st.markdown("- не указано")
        return

    rendered_any = False
    for item in evidence:
        if isinstance(item, dict):
            source = _stringify_value(item.get("source")) or "источник не указан"
            page = _stringify_value(item.get("page"))
            reason = _stringify_value(item.get("reason"))
            parts = [source]
            if page:
                parts.append(f"page {page}")
            if reason:
                parts.append(reason)
            st.markdown(f"- {', '.join(parts)}")
            rendered_any = True
            continue

        text = _stringify_value(item)
        if text:
            st.markdown(f"- {text}")
            rendered_any = True

    if not rendered_any:
        st.markdown("- не указано")


def clean_hypothesis_title(title: str, index: int) -> str:
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


def render_hypothesis_card(
    hypothesis: dict,
    index: int,
    debug_mode: bool = False,
    parent=None,
):
    clean_title = clean_hypothesis_title(hypothesis.get("title"), index)
    label = f"Гипотеза {index}: {clean_title}"

    expander_host = parent if parent is not None else st
    with expander_host.expander(label, expanded=False):

        description = _stringify_value(hypothesis.get("description"))
        if description:
            st.markdown("**Описание:**")
            st.write(description)

        mechanism = _stringify_value(hypothesis.get("mechanism"))
        if mechanism:
            st.markdown("**Механизм:**")
            st.write(mechanism)

        reason = _stringify_value(hypothesis.get("reason"))
        if reason:
            st.markdown("**Почему появилась:**")
            st.write(reason)

        expected_effect = _stringify_value(hypothesis.get("expected_effect"))
        if expected_effect:
            st.markdown("**Ожидаемый эффект:**")
            st.write(expected_effect)

        novelty = _stringify_value(hypothesis.get("novelty"))
        if novelty:
            st.markdown("**Новизна:**")
            st.write(novelty)

        st.markdown("**Ресурсы:**")
        _render_bullet_list(hypothesis.get("required_resources") or [])

        st.markdown("**План проверки:**")
        _render_numbered_list(hypothesis.get("verification_plan") or [])

        st.markdown("**Источники:**")
        _render_evidence_list(hypothesis.get("evidence") or [])

        confidence = _stringify_value(hypothesis.get("confidence")) or "не указано"
        priority = _stringify_value(hypothesis.get("priority")) or "не указано"
        st.markdown(f"**Уверенность:** {confidence}")
        st.markdown(f"**Приоритет:** {priority}")


        if debug_mode:
            with st.expander("DEBUG: raw hypothesis", expanded=False):
                st.json(hypothesis)


def render_progressive_hypotheses(
    debug_mode: bool,
    hypotheses=None,
    start_index: int = 1,
    parent=None,
):
    progressive_hypotheses = (
        hypotheses if hypotheses is not None else st.session_state.progressive_hypotheses
    )
    for index, hypothesis in enumerate(
        progressive_hypotheses[start_index - 1:],
        start=start_index,
    ):
        render_hypothesis_card(
            hypothesis,
            index,
            debug_mode=debug_mode,
            parent=parent,
        )


def extract_response_text(response):
    value = getattr(response, "output_text", "")
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def parse_json_like(value):
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    if not stripped:
        return None

    candidates = [stripped]

    if "```json" in stripped:
        start = stripped.find("```json") + len("```json")
        end = stripped.find("```", start)
        if end != -1:
            candidates.append(stripped[start:end].strip())

    first_brace = min(
        [idx for idx in [stripped.find("{"), stripped.find("[")] if idx != -1],
        default=-1,
    )
    if first_brace != -1:
        last_object = stripped.rfind("}")
        last_array = stripped.rfind("]")
        last_delim = max(last_object, last_array)
        if last_delim > first_brace:
            candidates.append(stripped[first_brace:last_delim + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    return None


def normalize_hypothesis(raw_text):
    parsed = parse_json_like(raw_text)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        return parsed[0]
    return {"raw_response": raw_text}


def serialize_hypotheses(hypotheses):
    return json.dumps(hypotheses, ensure_ascii=False, indent=2)


def split_into_chunks(text: str, chunk_size: int = 12000):
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def render_content(content):
    if isinstance(content, (dict, list)):
        st.json(content)
        return
    parsed = parse_json_like(content)
    if parsed is not None:
        st.json(parsed)
    else:
        st.text(content if isinstance(content, str) else str(content))


def render_block(title, content):
    with st.expander(title, expanded=False):
        render_content(content)


def preview_text(text, limit=1500):
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n... [truncated, total length: {len(text)}]"


def debug_panel(debug_enabled, title, payload, expanded=False):
    if not debug_enabled:
        return
    with st.expander(f"DEBUG: {title}", expanded=expanded):
        if isinstance(payload, (dict, list)):
            st.json(payload)
        else:
            st.text(str(payload))


def ensure_non_empty(stage_name, value):
    if value and value.strip():
        return value
    raise RuntimeError(f"Этап '{stage_name}' вернул пустой ответ.")


def initialize_session_state():
    for key, value in SESSION_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value.copy() if isinstance(value, (dict, list)) else value


def clear_generation_results():
    for key in [
        "structured_kpi",
        "literature_analysis",
        "patterns",
        "hypotheses",
        "critique",
        "final_report",
        "file_statuses",
        "stage_outputs_preview",
        "errors",
        "traceback",
        "completed_stages",
        "debug_prompt",
        "debug_constraints",
        "debug_file_list",
        "debug_file_text_lengths",
        "debug_file_errors",
        "literature_context_length",
        "debug_literature_context_preview",
        "progressive_hypotheses",
        "completed_hypothesis_count",
        "current_hypothesis_index",
        "progressive_generation_error",
        "debug_previous_hypotheses",
        "generation_completed_at",
    ]:
        value = SESSION_DEFAULTS[key]
        st.session_state[key] = value.copy() if isinstance(value, (dict, list)) else value
    st.session_state.is_generating = False
    st.session_state.generation_requested = False


def start_generation():
    st.session_state.is_generating = True
    st.session_state.generation_requested = True


def persist_stage_output(stage_key, value):
    st.session_state.completed_stages = list(dict.fromkeys([*st.session_state.completed_stages, stage_key]))
    st.session_state.stage_outputs_preview[stage_key] = {
        "length": len(value),
        "preview": preview_text(value, 800),
    }


def build_literature_entry(file_name, suffix, extracted_text):
    if suffix in {".xlsx", ".xls"}:
        return extracted_text.replace(
            "=== SHEET: ",
            f"=== FILE: {file_name} / SHEET: ",
        )
    return f"=== FILE: {file_name} ===\n{extracted_text}"


def render_saved_results():
    debug_enabled = st.session_state.debug_enabled
    progressive_hypotheses_container = None

    if st.session_state.file_statuses:
        with st.expander("Загруженные файлы и статус чтения", expanded=True):
            for item in st.session_state.file_statuses:
                st.write(
                    f"{item['name']} | {item['extension']} | {item['status_label']} | "
                    f"объём текста: {item['text_length']}"
                )
                if item["message"]:
                    st.caption(item["message"])

    if st.session_state.structured_kpi:
        render_block("Структурированный KPI", st.session_state.structured_kpi)
    if st.session_state.literature_analysis:
        render_block("Анализ литературы", st.session_state.literature_analysis)
    if st.session_state.patterns:
        render_block("Паттерны", st.session_state.patterns)
    if st.session_state.progressive_hypotheses or st.session_state.is_generating:
        st.subheader("Гипотезы")
        progressive_hypotheses_container = st.container()
        render_progressive_hypotheses(
            debug_mode=debug_enabled,
            parent=progressive_hypotheses_container,
        )
    elif st.session_state.hypotheses:
        render_block("Гипотезы", st.session_state.hypotheses)
    if st.session_state.critique:
        render_block("Критика", st.session_state.critique)
    if st.session_state.final_report:
        st.subheader("Итоговый отчёт")
        render_hypotheses(st.session_state.final_report)

    if should_enable_pdf_download(st.session_state):
        try:
            pdf_bytes = build_report_pdf(
                st.session_state,
                st.session_state.kpi_problem_text,
                st.session_state.constraints_text,
            )
        except Exception as exc:
            st.warning(f"Не удалось подготовить PDF-отчёт: {exc}")
        else:
            st.download_button(
                label="Скачать отчёт PDF",
                data=pdf_bytes,
                file_name=f"hypothesis_report_{datetime.now():%Y%m%d_%H%M%S}.pdf",
                mime="application/pdf",
            )

    debug_panel(debug_enabled, "Итог чтения файлов", st.session_state.file_statuses, expanded=True)
    debug_panel(
        debug_enabled,
        "Объединённый literature_context",
        st.session_state.debug_literature_context_preview,
    )
    debug_panel(debug_enabled, "Собранный prompt", st.session_state.debug_prompt, expanded=True)
    debug_panel(
        debug_enabled,
        "Состояние этапов",
        {
            "constraints": st.session_state.debug_constraints,
            "file_list": st.session_state.debug_file_list,
            "file_text_lengths": st.session_state.debug_file_text_lengths,
            "file_errors": st.session_state.debug_file_errors,
            "literature_context_length": st.session_state.literature_context_length,
            "completed_stages": st.session_state.completed_stages,
            "stage_outputs_preview": st.session_state.stage_outputs_preview,
            "errors": st.session_state.errors,
            "progressive_hypotheses": st.session_state.progressive_hypotheses,
            "completed_hypothesis_count": st.session_state.completed_hypothesis_count,
            "current_hypothesis_index": st.session_state.current_hypothesis_index,
            "progressive_generation_error": st.session_state.progressive_generation_error,
            "previous_hypotheses_history": st.session_state.debug_previous_hypotheses,
        },
        expanded=bool(st.session_state.completed_stages or st.session_state.errors),
    )
    if st.session_state.traceback:
        debug_panel(debug_enabled, "Traceback", st.session_state.traceback, expanded=True)

    return progressive_hypotheses_container


def process_uploaded_files(uploaded_files):
    results = []
    literature_parts = []

    for uploaded_file in uploaded_files:
        suffix = Path(uploaded_file.name).suffix.lower()
        temp_path = None

        if suffix not in SUPPORTED_EXTENSIONS:
            results.append(
                {
                    "name": uploaded_file.name,
                    "extension": suffix or "unknown",
                    "status": "error",
                    "status_label": "Ошибка чтения",
                    "message": "Неподдерживаемый тип файла.",
                    "text_length": 0,
                }
            )
            continue

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(uploaded_file.getbuffer())
                temp_path = temp_file.name

            extracted = read_file(temp_path)
            extracted_text = extracted if isinstance(extracted, str) else str(extracted)
            extracted_text = extracted_text.strip()

            if extracted_text:
                literature_parts.append(build_literature_entry(uploaded_file.name, suffix, extracted_text))
                results.append(
                    {
                        "name": uploaded_file.name,
                        "extension": suffix,
                        "status": "success",
                        "status_label": "Успешно прочитан",
                        "message": "",
                        "text_length": len(extracted_text),
                    }
                )
            else:
                results.append(
                    {
                        "name": uploaded_file.name,
                        "extension": suffix,
                        "status": "error",
                        "status_label": "Ошибка чтения",
                        "message": "Файл прочитан, но извлечённый текст пуст.",
                        "text_length": 0,
                    }
                )
        except Exception as exc:
            results.append(
                {
                    "name": uploaded_file.name,
                    "extension": suffix,
                    "status": "error",
                    "status_label": "Ошибка чтения",
                    "message": str(exc),
                    "text_length": 0,
                }
            )
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    return results, "\n\n".join(literature_parts)


def main():
    st.set_page_config(page_title="Фабрика гипотез", layout="wide")
    initialize_session_state()
    st.title("Фабрика гипотез")

    is_generating = st.session_state.get("is_generating", False)

    with st.sidebar:
        debug_enabled = st.session_state.get("debug_enabled", DEFAULT_DEBUG)
        if is_generating:
            st.toggle(
                "Режим отладки",
                value=debug_enabled,
                disabled=True,
            )
            debug_hint = (
                "Генерация выполняется. Режим отладки временно заблокирован, "
                "чтобы не прервать процесс. Debug-данные всё равно сохраняются."
            )
        else:
            debug_enabled = st.toggle(
                "Режим отладки",
                value=debug_enabled,
            )
            st.session_state.debug_enabled = debug_enabled
            if debug_enabled:
                debug_hint = (
                    "Режим отладки включён: отображаются входы, выходы, статусы этапов "
                    "и ошибки. Можно выключить после завершения генерации."
                )
            else:
                debug_hint = (
                    "Режим отладки выключен: debug-данные скрыты, но будут сохраняться "
                    "при генерации и доступны после включения."
                )

        st.caption(debug_hint)
        if st.button("Очистить результаты", disabled=is_generating):
            clear_generation_results()

    uploaded_files = st.file_uploader(
        "Загрузите PDF или Excel файлы",
        type=["pdf", "xlsx", "xls"],
        accept_multiple_files=True,
    )
    kpi_problem = st.text_area("KPI / технологическая проблема", height=150)
    constraints = st.text_area("Ограничения", height=120)
    st.session_state.kpi_problem_text = kpi_problem.strip()
    st.session_state.constraints_text = constraints.strip()

    saved_results_placeholder = st.empty()
    with saved_results_placeholder.container():
        progressive_hypotheses_container = render_saved_results()

    st.button(
        "Сгенерировать гипотезы",
        type="primary",
        on_click=start_generation,
        disabled=is_generating,
    )

    if not st.session_state.get("generation_requested", False):
        return

    try:
        st.session_state.generation_requested = False

        if not uploaded_files:
            st.warning("Загрузите хотя бы один PDF или Excel файл.")
            return

        clear_generation_results()
        st.session_state.is_generating = True
        st.session_state.kpi_problem_text = kpi_problem.strip()
        st.session_state.constraints_text = constraints.strip()
        st.session_state.debug_constraints = constraints.strip()
        st.session_state.debug_file_list = [uploaded_file.name for uploaded_file in uploaded_files]
        with saved_results_placeholder.container():
            progressive_hypotheses_container = render_saved_results()

        file_results, literature_context = process_uploaded_files(uploaded_files)
        st.session_state.file_statuses = file_results
        st.session_state.debug_file_text_lengths = {
            item["name"]: item["text_length"] for item in file_results
        }
        st.session_state.debug_file_errors = {
            item["name"]: item["message"]
            for item in file_results
            if item["status"] == "error" and item["message"]
        }
        st.session_state.literature_context_length = len(literature_context)
        st.session_state.debug_literature_context_preview = preview_text(literature_context)

        if not literature_context.strip():
            st.session_state.errors = "Нет успешно прочитанных источников"
            with saved_results_placeholder.container():
                render_saved_results()
            st.error("Нет успешно прочитанных источников")
            return

        prompt = f"{kpi_problem.strip()}\n\nОграничения:\n{constraints.strip()}".strip()
        st.session_state.debug_prompt = prompt

        if not kpi_problem.strip():
            st.session_state.errors = "KPI / технологическая проблема не заполнена."
            st.warning("Заполните поле KPI / технологическая проблема.")
            return

        with st.spinner("Выполняется анализ..."):
            structured_kpi = analyze_kpi(prompt)
            structured_kpi_text = ensure_non_empty(
                "analyze_kpi",
                extract_response_text(structured_kpi),
            )
            st.session_state.structured_kpi = structured_kpi_text
            persist_stage_output("analyze_kpi", structured_kpi_text)

            chunks = split_into_chunks(literature_context, 50000)
            all_results = []
            article_progress_placeholder = st.empty()
            article_progress = article_progress_placeholder.progress(0)

            for index, chunk in enumerate(chunks):
                result = analyze_articles(structured_kpi_text, chunk)
                text = extract_response_text(result)
                if text:
                    all_results.append(text)
                article_progress.progress((index + 1) / len(chunks))

            article_progress_placeholder.empty()

            literature_analysis_text = ensure_non_empty(
                "analyze_articles",
                "\n".join(all_results),
            )
            st.session_state.literature_analysis = literature_analysis_text
            persist_stage_output("analyze_articles", literature_analysis_text)

            patterns = find_patterns(literature_analysis_text)
            patterns_text = ensure_non_empty(
                "patterns_text",
                extract_response_text(patterns),
            )
            st.session_state.patterns = patterns_text
            persist_stage_output("patterns_text", patterns_text)

            hypothesis_status_placeholder = st.empty()
            hypothesis_progress_placeholder = st.empty()
            hypothesis_progress = hypothesis_progress_placeholder.progress(0.0)

            for hypothesis_index in range(1, TOTAL_HYPOTHESES + 1):
                st.session_state.current_hypothesis_index = hypothesis_index
                hypothesis_status_placeholder.text(
                    f"Генерируется гипотеза {hypothesis_index}/{TOTAL_HYPOTHESES}..."
                )

                previous_hypotheses_payload = serialize_hypotheses(st.session_state.progressive_hypotheses)
                st.session_state.debug_previous_hypotheses.append(
                    {
                        "hypothesis_index": hypothesis_index,
                        "previous_hypotheses": previous_hypotheses_payload,
                    }
                )

                try:
                    hypothesis_response = generate_single_hypothesis(
                        prompt,
                        constraints.strip(),
                        literature_context,
                        structured_kpi_text,
                        literature_analysis_text,
                        patterns_text,
                        previous_hypotheses_payload,
                        hypothesis_index=hypothesis_index,
                        total_hypotheses=TOTAL_HYPOTHESES,
                    )
                    hypothesis_text = ensure_non_empty(
                        f"generate_single_hypothesis_{hypothesis_index}",
                        extract_response_text(hypothesis_response),
                    )
                except Exception as exc:
                    st.session_state.progressive_generation_error = (
                        f"Ошибка при генерации гипотезы {hypothesis_index}"
                    )
                    raise RuntimeError(
                        f"{st.session_state.progressive_generation_error}: {exc}"
                    ) from exc

                st.session_state.progressive_hypotheses.append(normalize_hypothesis(hypothesis_text))
                st.session_state.completed_hypothesis_count = len(st.session_state.progressive_hypotheses)
                if st.session_state.completed_hypothesis_count == TOTAL_HYPOTHESES:
                    st.session_state.generation_completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state.hypotheses = serialize_hypotheses(st.session_state.progressive_hypotheses)
                persist_stage_output("generate_hypothesis", st.session_state.hypotheses)

                hypothesis_progress.progress(
                    st.session_state.completed_hypothesis_count / TOTAL_HYPOTHESES
                )
                if progressive_hypotheses_container is None:
                    with saved_results_placeholder.container():
                        progressive_hypotheses_container = render_saved_results()
                render_progressive_hypotheses(
                    debug_mode=st.session_state.debug_enabled,
                    hypotheses=st.session_state.progressive_hypotheses,
                    start_index=st.session_state.completed_hypothesis_count,
                    parent=progressive_hypotheses_container,
                )

            hypothesis_status_placeholder.text("Генерация гипотез завершена. Выполняется рецензирование...")
            hypotheses_text = st.session_state.hypotheses

            critique = review(hypotheses_text, prompt)
            critique_text = ensure_non_empty(
                "review",
                extract_response_text(critique),
            )
            st.session_state.critique = critique_text
            persist_stage_output("review", critique_text)

            final_output = explain(critique_text)
            final_output_text = ensure_non_empty(
                "explain",
                extract_response_text(final_output),
            )
            st.session_state.final_report = final_output_text
            st.session_state.generation_completed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            persist_stage_output("explain", final_output_text)
            with saved_results_placeholder.container():
                render_saved_results()
            hypothesis_status_placeholder.empty()
            hypothesis_progress_placeholder.empty()
            st.session_state.errors = ""
            st.session_state.traceback = ""
    except Exception as exc:
        st.session_state.errors = st.session_state.progressive_generation_error or str(exc)
        st.session_state.traceback = traceback.format_exc()
        with saved_results_placeholder.container():
            render_saved_results()
        st.error(
            f"{st.session_state.errors}. Подробности: {exc}"
        )
        return
    finally:
        should_rerun = (
            st.session_state.get("is_generating", False)
            or st.session_state.get("generation_requested", False)
        )
        st.session_state.is_generating = False
        st.session_state.generation_requested = False
        if should_rerun:
            st.rerun()

    with saved_results_placeholder.container():
        render_saved_results()


if __name__ == "__main__":
    main()
