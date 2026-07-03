import fitz  # Импортируем PyMuPDF
import pandas as pd

def pdf(fileName):
    text = ""
    doc = fitz.open(fileName)
    for page in doc:
        text += page.get_text()
    return text

def xlsx(fileName):

    df = pd.read_excel(fileName)

    return df.head()

