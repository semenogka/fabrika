from pipeline import analyze_articles, analyze_kpi, explain, generate_hypothesis, review
from reader import read_file


if __name__ == "__main__":
    kpi = "Повысить извлечение никеля без увеличения энергозатрат."
    limitations = "Ограничения: бюджет, оборудование, сырьё, нормативы."
    prompt = f"{kpi}\n\n{limitations}"

    parsed = analyze_kpi(prompt)
    print(parsed.output_text)

    literature_text = read_file(
        r"files\geokniga_lodeyshchikovvvtehnologiyaizvlecheniyazolotaiserebraizupornyh1.pdf"
    )
    knowledge = analyze_articles(parsed.output_text, literature_text)
    print(knowledge.output_text)

    if knowledge.output_text:
        hypothesis = generate_hypothesis(knowledge.output_text)
        reviewed = review(hypothesis.output_text)
        result = explain(reviewed.output_text)
        print(result.output_text)
