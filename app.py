import json
import os
import re
import tempfile
import traceback
from pathlib import Path

import streamlit as st

from pipeline import analyze_articles, analyze_kpi, explain, find_patterns, generate_hypothesis, review
from reader import read_file


SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls"}
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


def split_into_chunks(text: str, chunk_size: int = 12000):
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]


def render_content(content):
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
    if st.session_state.hypotheses:
        render_block("Гипотезы", st.session_state.hypotheses)
    if st.session_state.critique:
        render_block("Критика", st.session_state.critique)
    if st.session_state.final_report:
        st.subheader("Итоговый отчёт")
        render_hypotheses(st.session_state.final_report)

    debug_enabled = st.session_state.debug_enabled
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
        },
        expanded=bool(st.session_state.completed_stages or st.session_state.errors),
    )
    if st.session_state.traceback:
        debug_panel(debug_enabled, "Traceback", st.session_state.traceback, expanded=True)


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

    render_saved_results()

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
        st.session_state.debug_constraints = constraints.strip()
        st.session_state.debug_file_list = [uploaded_file.name for uploaded_file in uploaded_files]

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
            progress = st.progress(0)

            for index, chunk in enumerate(chunks):
                result = analyze_articles(structured_kpi_text, chunk)
                text = extract_response_text(result)
                if text:
                    all_results.append(text)
                progress.progress((index + 1) / len(chunks))

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

            hypotheses = generate_hypothesis(structured_kpi_text, literature_analysis_text, patterns_text)
            hypotheses_text = ensure_non_empty(
                "generate_hypothesis",
                extract_response_text(hypotheses),
            )
            st.session_state.hypotheses = hypotheses_text
            persist_stage_output("generate_hypothesis", hypotheses_text)

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
            persist_stage_output("explain", final_output_text)
            st.session_state.errors = ""
            st.session_state.traceback = ""
    except Exception as exc:
        st.session_state.errors = str(exc)
        st.session_state.traceback = traceback.format_exc()
        render_saved_results()
        st.error(
            "Ошибка при обращении к модели или обработке данных. "
            f"Подробности: {exc}"
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

    render_saved_results()


if __name__ == "__main__":
    main()
