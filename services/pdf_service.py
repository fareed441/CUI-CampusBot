import re


CLASS_CODE_REGEX = r"[A-Z]{2,}-[A-Z]{2}\d{2}-[A-Z0-9]+"


def normalize_class_code(text: str) -> str:
    cleaned = (text or "").strip().upper()
    return cleaned.split("(")[0].strip()


def extract_class_codes(pdf_path: str):
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for timetable PDF extraction.") from exc

    extracted = []

    with fitz.open(pdf_path) as document:
        for page_number in range(len(document)):
            page = document[page_number]
            text = page.get_text()
            matches = re.findall(CLASS_CODE_REGEX, text)

            for match in matches:
                code = normalize_class_code(match)
                if code:
                    extracted.append(
                        {
                            "class_code": code,
                            "page_number": page_number,
                        }
                    )

    return extracted
