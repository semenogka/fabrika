import json
import os
import tempfile
import traceback
from pathlib import Path
import json
import re
import streamlit as st

from pipeline import analyze_articles, analyze_kpi, explain, generate_hypothesis, review, find_patterns
from reader import read_file


SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls"}
DEFAULT_DEBUG = os.getenv("STREAMLIT_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}



def split_hypotheses(text):

    parts = re.split(r"(?=Гипотеза\s+\d+:)", text)

    return [p.strip() for p in parts if p.strip()]

def render_hypotheses(text: str):
    # Делим текст по заголовкам "Гипотеза N"
    parts = re.split(r'(?=\*\*Гипотеза\s+\d+:)', text)

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
    return [
        text[i:i + chunk_size]
        for i in range(0, len(text), chunk_size)
    ]

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
                    "type": suffix or "unknown",
                    "status": "error",
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
                literature_parts.append(f"=== FILE: {uploaded_file.name} ===\n{extracted_text}")
                results.append(
                    {
                        "name": uploaded_file.name,
                        "type": suffix,
                        "status": "success",
                        "message": "Успешно прочитан",
                        "text_length": len(extracted_text),
                    }
                )
            else:
                results.append(
                    {
                        "name": uploaded_file.name,
                        "type": suffix,
                        "status": "error",
                        "message": "Файл прочитан, но извлечённый текст пуст.",
                        "text_length": 0,
                    }
                )
        except Exception as exc:
            results.append(
                {
                    "name": uploaded_file.name,
                    "type": suffix,
                    "status": "error",
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
    st.title("Фабрика гипотез")

    with st.sidebar:
        debug_enabled = st.toggle("Режим отладки", value=DEFAULT_DEBUG)
        st.caption("Показывает входы, выходы и стек ошибок. Можно отключить в любой момент.")

    uploaded_files = st.file_uploader(
        "Загрузите PDF или Excel файлы",
        type=["pdf", "xlsx", "xls"],
        accept_multiple_files=True,
    )
    kpi_problem = st.text_area("KPI / технологическая проблема", height=150)
    constraints = st.text_area("Ограничения", height=120)

    if st.button("Сгенерировать гипотезы", type="primary"):
        if not uploaded_files:
            st.warning("Загрузите хотя бы один PDF или Excel файл.")
            return

        file_results, literature_context = process_uploaded_files(uploaded_files)

        with st.expander("Загруженные файлы и статус чтения", expanded=True):
            for item in file_results:
                st.write(
                    f"{item['name']} | {item['type']} | {item['message']} | "
                    f"объём текста: {item['text_length']}"
                )

        debug_panel(debug_enabled, "Итог чтения файлов", file_results, expanded=True)
        debug_panel(
            debug_enabled,
            "Объединённый literature_context",
            preview_text(literature_context),
        )

        if not literature_context.strip():
            st.error("Не удалось прочитать ни один файл. Пайплайн не был запущен.")
            return

        prompt = f"{kpi_problem.strip()}\n\nОграничения:\n{constraints.strip()}".strip()
        debug_panel(debug_enabled, "Собранный prompt", prompt, expanded=True)

        if not kpi_problem.strip():
            st.warning("Заполните поле KPI / технологическая проблема.")
            return

        stage_outputs = {}

        try:
            with st.spinner("Выполняется анализ..."):
                structured_kpi = analyze_kpi(prompt)
                structured_kpi_text = ensure_non_empty(
                    "analyze_kpi",
                    extract_response_text(structured_kpi),
                )
                stage_outputs["analyze_kpi"] = structured_kpi_text
                # literature_context = literature_context[:50000]
                chunks = split_into_chunks(literature_context, 50000)

                all_results = []

                progress = st.progress(0)

                for i, chunk in enumerate(chunks):

                    result = analyze_articles(
                        structured_kpi_text,
                        chunk,
                    )

                    text = extract_response_text(result)

                    if text:
                        all_results.append(text)

                    progress.progress((i + 1) / len(chunks))

                literature_analysis_text = "\n".join(all_results)

                literature_analysis_text = ensure_non_empty(
                    "analyze_articles",
                    literature_analysis_text,
                )
                stage_outputs["analyze_articles"] = literature_analysis_text
                patterns = find_patterns(literature_analysis_text)
                patterns_text = ensure_non_empty(
                    "patterns_text",
                    extract_response_text(patterns),
                )
                stage_outputs["patterns_text"] = patterns_text
                hypotheses = generate_hypothesis(structured_kpi_text, literature_analysis_text, patterns_text)
                hypotheses_text = ensure_non_empty(
                    "generate_hypothesis",
                    extract_response_text(hypotheses),
                )
                stage_outputs["generate_hypothesis"] = hypotheses_text

                critique = review(hypotheses_text, prompt)
                critique_text = ensure_non_empty(
                    "review",
                    extract_response_text(critique),
                )
                stage_outputs["review"] = critique_text

                final_output = explain(critique_text)
                final_output_text = ensure_non_empty(
                    "explain",
                    extract_response_text(final_output),
                )
                stage_outputs["explain"] = final_output_text
        except Exception as exc:
            st.error(
                "Ошибка при обращении к модели или обработке данных. "
                f"Подробности: {exc}"
            )
            debug_panel(
                debug_enabled,
                "Состояние этапов до ошибки",
                {
                    "prompt_length": len(prompt),
                    "literature_context_length": len(literature_context),
                    "completed_stages": list(stage_outputs.keys()),
                    "stage_outputs_preview": {
                        key: preview_text(value, 800) for key, value in stage_outputs.items()
                    },
                },
                expanded=True,
            )
            debug_panel(
                debug_enabled,
                "Traceback",
                traceback.format_exc(),
                expanded=True,
            )
            return

        debug_panel(
            debug_enabled,
            "Выходы этапов пайплайна",
            {
                key: {
                    "length": len(value),
                    "preview": preview_text(value, 800),
                }
                for key, value in stage_outputs.items()
            },
        )

        render_block("Структурированный KPI", structured_kpi_text)
        render_block("Анализ литературы", literature_analysis_text)
        render_block("Гипотезы", hypotheses_text)
        render_block("Критика", critique_text)
        st.subheader("Итоговый отчёт")
        render_hypotheses(final_output_text)



if __name__ == "__main__":
    main()
