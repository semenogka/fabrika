import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from pipeline import analyze_articles, analyze_kpi, explain, generate_hypothesis, review
from reader import read_file


SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls"}


def extract_response_text(response):
    return getattr(response, "output_text", str(response))


def parse_json_like(value):
    if not isinstance(value, str):
        return None

    stripped = value.strip()
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


def render_block(title, content):
    with st.expander(title, expanded=False):
        parsed = parse_json_like(content)
        if parsed is not None:
            st.json(parsed)
        else:
            st.text(content if isinstance(content, str) else str(content))


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
                literature_parts.append(
                    f"=== FILE: {uploaded_file.name} ===\n{extracted_text}"
                )
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

        if not literature_context.strip():
            st.error("Не удалось прочитать ни один файл. Пайплайн не был запущен.")
            return

        prompt = f"{kpi_problem.strip()}\n\nОграничения:\n{constraints.strip()}".strip()

        if not prompt:
            st.warning("Заполните поле KPI / технологическая проблема.")
            return

        try:
            with st.spinner("Выполняется анализ..."):
                structured_kpi = analyze_kpi(prompt)
                structured_kpi_text = extract_response_text(structured_kpi)

                literature_analysis = analyze_articles(
                    structured_kpi_text,
                    literature_context,
                )
                literature_analysis_text = extract_response_text(literature_analysis)

                hypotheses = generate_hypothesis(literature_analysis_text)
                hypotheses_text = extract_response_text(hypotheses)

                critique = review(hypotheses_text)
                critique_text = extract_response_text(critique)

                final_output = explain(critique_text)
                final_output_text = extract_response_text(final_output)
        except Exception as exc:
            st.error(
                "Ошибка при обращении к модели или обработке данных. "
                f"Подробности: {exc}"
            )
            return

        render_block("Структурированный KPI", structured_kpi_text)
        render_block("Анализ литературы", literature_analysis_text)
        render_block("Гипотезы", hypotheses_text)
        render_block("Критика", critique_text)
        render_block("Финальный вывод", final_output_text)


if __name__ == "__main__":
    main()
