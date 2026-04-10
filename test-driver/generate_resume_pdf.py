"""Generate a PDF resume from the resume template JSON.

Usage:
    python generate_resume_pdf.py [output.pdf]

Generates from resume_template.json in the same directory.
Default output: alex_green_resume.pdf in the current directory.
"""

import json
import sys
from pathlib import Path

from fpdf import FPDF


def _safe(text: str) -> str:
    """Replace Unicode characters that Helvetica (latin-1) cannot render."""
    return (
        text
        .replace("\u2014", " - ")   # em dash
        .replace("\u2013", " - ")   # en dash
        .replace("\u2022", "-")     # bullet
        .replace("\u2018", "'")     # left single quote
        .replace("\u2019", "'")     # right single quote
        .replace("\u201c", '"')     # left double quote
        .replace("\u201d", '"')     # right double quote
    )


def generate_resume_pdf(resume_data: dict, output_path: Path) -> None:
    """Render *resume_data* (the resume_template.json structure) to a PDF at *output_path*."""

    header = resume_data["header"]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # -- Header -----------------------------------------------------------
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 10, _safe(header["name"]), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, _safe(header["title"]), new_x="LMARGIN", new_y="NEXT", align="C")

    contact_parts = [header.get("email", ""), header.get("location", "")]
    contact_line = "  |  ".join(p for p in contact_parts if p)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, _safe(contact_line), new_x="LMARGIN", new_y="NEXT", align="C")

    pdf.ln(2)
    _draw_line(pdf)

    # -- Summary ----------------------------------------------------------
    if resume_data.get("summary"):
        _section_heading(pdf, "Summary")
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 5, _safe(resume_data["summary"]))
        pdf.ln(2)

    # -- Experience -------------------------------------------------------
    if resume_data.get("experience"):
        _section_heading(pdf, "Experience")
        for job in resume_data["experience"]:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 5, _safe(f"{job['title']}  -  {job['company']}"),
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(0, 5, _safe(f"{job.get('location', '')}    {job.get('dates', '')}"),
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            for bullet in job.get("bullets", []):
                x = pdf.get_x()
                pdf.cell(5, 4.5, "-")
                pdf.multi_cell(0, 4.5, _safe(bullet))
                pdf.set_x(x)
            pdf.ln(2)

    # -- Education --------------------------------------------------------
    if resume_data.get("education"):
        _section_heading(pdf, "Education")
        for edu in resume_data["education"]:
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 5, _safe(f"{edu['degree']}  -  {edu['institution']}"),
                     new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "I", 9)
            pdf.cell(0, 5, _safe(edu.get("dates", "")), new_x="LMARGIN", new_y="NEXT")
            if edu.get("detail"):
                pdf.set_font("Helvetica", "", 9)
                pdf.multi_cell(0, 4.5, _safe(edu["detail"]))
            pdf.ln(1)

    # -- Skills -----------------------------------------------------------
    if resume_data.get("skills"):
        _section_heading(pdf, "Skills")
        pdf.set_font("Helvetica", "", 9)
        for category, items in resume_data["skills"].items():
            label = category.replace("_", " ").title()
            pdf.cell(0, 5, _safe(f"{label}: {', '.join(items)}"),
                     new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # -- Certifications ---------------------------------------------------
    if resume_data.get("certifications"):
        _section_heading(pdf, "Certifications")
        pdf.set_font("Helvetica", "", 9)
        for cert in resume_data["certifications"]:
            pdf.cell(5)
            pdf.cell(0, 5, _safe(f"-  {cert}"), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # -- Languages --------------------------------------------------------
    if resume_data.get("languages"):
        _section_heading(pdf, "Languages")
        pdf.set_font("Helvetica", "", 9)
        langs = [f"{l['language']} ({l['proficiency']})" for l in resume_data["languages"]]
        pdf.cell(0, 5, _safe(", ".join(langs)), new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(output_path))


def _section_heading(pdf: FPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    _draw_line(pdf)


def _draw_line(pdf: FPDF) -> None:
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(2)


if __name__ == "__main__":
    template = Path(__file__).resolve().parent / "resume_template.json"
    data = json.loads(template.read_text())
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("alex_green_resume.pdf")
    generate_resume_pdf(data, out)
    print(f"Generated: {out.resolve()}")
