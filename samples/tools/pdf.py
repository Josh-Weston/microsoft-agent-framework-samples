import os
from pypdf import PdfReader
from typing import Annotated
from pydantic import Field
from agent_framework import tool


@tool(
    name="extract_text_from_pdf",
    description="Extract text from a PDF file. Use this when you need to read a .pdf resource from a skill's references or assets folder."
)
def extract_text_from_pdf(file_path: Annotated[str, Field(description="The path to the PDF file (e.g., 'skills/blog-writer/references/analysis.pdf'")]) -> str:
    """
    Extracts text from a PDF file. Use this when you need to read 
    a .pdf resource from a skill's references or assets folder.

    Args:
        file_path: The path to the PDF file (e.g., 'skills/blog-writer/references/analysis.pdf')
    """
    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    try:
        reader = PdfReader(file_path)
        text = [page.extract_text() for page in reader.pages]
        return "\n".join(text)
    except Exception as e:
        return f"Error reading PDF: {str(e)}"
