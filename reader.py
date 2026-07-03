from pathlib import Path


def pdf(file_name):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is not installed. Install dependencies from requirements.txt.") from exc

    text = ""
    with fitz.open(file_name) as doc:
        for page in doc:
            text += page.get_text()
    return text


def xlsx(file_name):
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is not installed. Install dependencies from requirements.txt.") from exc

    sheets = pd.read_excel(file_name, sheet_name=None)
    parts = []

    for sheet_name, dataframe in sheets.items():
        parts.append(f"Sheet: {sheet_name}")
        parts.append(dataframe.fillna("").to_string(index=False))

    return "\n\n".join(parts)


def read_file(file_name):
    suffix = Path(file_name).suffix.lower()

    if suffix == ".pdf":
        return pdf(file_name)
    if suffix in {".xlsx", ".xls"}:
        return xlsx(file_name)

    raise ValueError(f"Unsupported file type: {suffix}")
