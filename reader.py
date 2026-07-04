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


def _normalize_cell(value, pd):
    if pd.isna(value):
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


def _format_sheet(dataframe, pd):
    cleaned = dataframe.dropna(axis=0, how="all").dropna(axis=1, how="all")

    if cleaned.empty and len(cleaned.columns) == 0:
        return "(empty sheet)"

    columns = [
        _normalize_cell(column, pd) or f"column_{index + 1}"
        for index, column in enumerate(cleaned.columns)
    ]
    lines = [" | ".join(columns)]

    for row in cleaned.itertuples(index=False, name=None):
        cells = [_normalize_cell(cell, pd) for cell in row]
        lines.append(" | ".join(cells))

    return "\n".join(lines)


def xlsx(file_name):
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is not installed. Install dependencies from requirements.txt.") from exc

    sheets = pd.read_excel(file_name, sheet_name=None)
    parts = []

    for sheet_name, dataframe in list(sheets.items())[:3]:
        parts.append(f"=== SHEET: {sheet_name} ===")
        parts.append(_format_sheet(dataframe, pd))

    return "\n\n".join(parts)


def read_file(file_name):
    suffix = Path(file_name).suffix.lower()

    if suffix == ".pdf":
        return pdf(file_name)
    if suffix in {".xlsx", ".xls"}:
        return xlsx(file_name)

    raise ValueError(f"Unsupported file type: {suffix}")
