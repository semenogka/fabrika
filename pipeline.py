import json

from config import DEEPSEEK_MODEL, FOLDER_ID, QWEN_MODEL, YANDEX_MODEL, client, GPT_MODEL
from prompts import (
    REVIEW_SYSTEM,
    REPORT_SYSTEM,
    HYPOTHESIS_SYSTEM,
    KPI_SYSTEM,
    KNOWLEDGE_SYSTEM,
    PATTERN_SYSTEM,
    SINGLE_HYPOTHESIS_SYSTEM,
)


def _model_uri(model_name):
    if not FOLDER_ID:
        raise RuntimeError("YANDEX_FOLDER_ID is not configured.")
    if not model_name:
        raise RuntimeError("Model name is not configured in .env.")
    return f"gpt://{FOLDER_ID}/{model_name}"


def analyze_kpi(kpi):
    return client.responses.create(
        model=_model_uri(YANDEX_MODEL),
        temperature=0.3,
        instructions=KPI_SYSTEM,
        input=kpi,
        max_output_tokens=500,
    )


def analyze_articles(parsed, text):
    return client.responses.create(
        model=_model_uri(DEEPSEEK_MODEL),
        temperature=0.3,
        instructions=KNOWLEDGE_SYSTEM,
        input=f"{parsed}\n\n{text}",
        max_output_tokens=8000,
    )


def generate_hypothesis(kpi, knowledge, patterns):
    return client.responses.create(
        model=_model_uri(DEEPSEEK_MODEL),
        temperature=0.3,
        instructions=HYPOTHESIS_SYSTEM,
        input = f"""
        KPI:
        {kpi}

        Извлеченные знания:
        {knowledge}

        Закономерности:
        {patterns}
        """,
        max_output_tokens=8000,
    )


def generate_single_hypothesis(
    kpi,
    constraints,
    literature_context,
    structured_kpi,
    literature_analysis,
    patterns_text,
    previous_hypotheses,
    hypothesis_index=1,
    total_hypotheses=5,
):
    previous_hypotheses_text = previous_hypotheses
    if not isinstance(previous_hypotheses_text, str):
        previous_hypotheses_text = json.dumps(previous_hypotheses, ensure_ascii=False, indent=2)

    return client.responses.create(
        model=_model_uri(DEEPSEEK_MODEL),
        temperature=0.3,
        instructions=SINGLE_HYPOTHESIS_SYSTEM,
        input=f"""
        KPI / технологическая проблема:
        {kpi}

        Ограничения:
        {constraints}

        Literature context:
        {literature_context}

        Structured KPI:
        {structured_kpi}

        Literature analysis:
        {literature_analysis}

        Patterns:
        {patterns_text}

        Previous hypotheses:
        {previous_hypotheses_text}

        Сгенерируй только одну новую гипотезу. Не повторяй и не перефразируй уже сгенерированные гипотезы. Это гипотеза номер {hypothesis_index} из {total_hypotheses}.
        """,
        max_output_tokens=8000,
    )

def find_patterns(data):
    return client.responses.create(
        model=_model_uri(GPT_MODEL),
        temperature=0.3,
        instructions=PATTERN_SYSTEM,
        input=data,
        max_output_tokens=8000,
    )

def review(hypothesis, kpi):
    return client.responses.create(
        model=_model_uri(DEEPSEEK_MODEL),
        temperature=0.3,
        instructions=REVIEW_SYSTEM,
        input= f"""
            KPI:{kpi}

            Гипотезы:{hypothesis}
            """,
            max_output_tokens=8000,
    )


def explain(data):
    return client.responses.create(
        model=_model_uri(YANDEX_MODEL),
        temperature=0.3,
        instructions=REPORT_SYSTEM,
        input=data,
        max_output_tokens=8000,
    )
