from pipeline import *
from reader import *
kpi = """
Повысить извлечение никеля
без увеличения энергозатрат.
"""

limitation = """
ограничения:
- бюджет
- оборудование
- сырье
- нормативы
"""

prompt = kpi + limitation
# 1
parsed = analyze_kpi(prompt)
print(parsed.output_text)

literature_text = pdf("files\geokniga_lodeyshchikovvvtehnologiyaizvlecheniyazolotaiserebraizupornyh1.pdf")
knowledge = analyze_articles(parsed.output_text, literature_text)
print(knowledge.output_text)
if knowledge != '':
    hypothesis = generate_hypothesis(knowledge.output_text)

    reviewed = review(hypothesis.output_text)

    result = explain(reviewed.output_text)

    print(result.output_text)
else:
    print(knowledge)