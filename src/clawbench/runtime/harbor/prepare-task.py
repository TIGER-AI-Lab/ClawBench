#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

PURELYMAIL_API = "https://purelymail.com/api/v0"


def env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip().strip('"').strip("'")
    return ""


def purelymail_request(endpoint: str, body: dict, api_key: str) -> dict:
    data = json.dumps(body).encode()
    req = Request(
        f"{PURELYMAIL_API}/{endpoint}",
        data=data,
        headers={"Purelymail-Api-Token": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def create_email(api_key: str, domain: str) -> tuple[str, str]:
    local = f"cb{uuid.uuid4().hex[:12]}"
    password = secrets.token_urlsafe(16)
    purelymail_request(
        "createUser",
        {
            "userName": local,
            "domainName": domain,
            "password": password,
            "enablePasswordReset": False,
            "sendWelcomeEmail": False,
        },
        api_key,
    )
    return f"{local}@{domain}", password


def safe_text(text: str) -> str:
    return (
        text.replace("\u2014", " - ")
        .replace("\u2013", " - ")
        .replace("\u2022", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


def write_resume_pdf(template_path: Path, email: str, output_path: Path) -> None:
    from fpdf import FPDF

    data = json.loads(template_path.read_text())
    data["header"]["email"] = email
    header = data["header"]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 10, safe_text(header["name"]), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, safe_text(header["title"]), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0,
        5,
        safe_text(
            "  |  ".join(
                p for p in [header.get("email", ""), header.get("location", "")] if p
            )
        ),
        new_x="LMARGIN",
        new_y="NEXT",
        align="C",
    )
    pdf.ln(2)
    for section in (
        "summary",
        "experience",
        "education",
        "skills",
        "certifications",
        "languages",
    ):
        value = data.get(section)
        if not value:
            continue
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 7, section.replace("_", " ").title(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        if isinstance(value, str):
            pdf.multi_cell(0, 5, safe_text(value))
        else:
            pdf.multi_cell(
                0, 5, safe_text(json.dumps(value, ensure_ascii=False, indent=2))
            )
        pdf.ln(1)
    pdf.output(str(output_path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare ClawBench task data for Harbor"
    )
    parser.add_argument("--task-json", type=Path, default=Path("/app/task.json"))
    parser.add_argument("--extra-info-dir", type=Path, default=Path("/app/extra_info"))
    parser.add_argument("--output-dir", type=Path, default=Path("/app/my-info"))
    parser.add_argument(
        "--state-file", type=Path, default=Path("/data/harbor-task-state.json")
    )
    args = parser.parse_args()

    api_key = env_value("PURELY_MAIL_API_KEY", "PURELYMAIL_API_KEY")
    domain = env_value("PURELY_MAIL_DOMAIN", "PURELYMAIL_DOMAIN")
    if not api_key or not domain:
        raise SystemExit("PURELY_MAIL_API_KEY and PURELY_MAIL_DOMAIN are required")

    email, password = create_email(api_key, domain)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.state_file.parent.mkdir(parents=True, exist_ok=True)

    personal_info = json.loads(
        Path("/app/src/shared/alex_green_personal_info.json").read_text()
    )
    personal_info["contact"]["email"] = email
    personal_info.pop("online_accounts", None)
    (args.output_dir / "alex_green_personal_info.json").write_text(
        json.dumps(personal_info, indent=2)
    )

    credentials = {
        "email": email,
        "password": password,
        "login_url": "https://purelymail.com/user/login",
        "provider": "PurelyMail",
    }
    (args.output_dir / "email_credentials.json").write_text(
        json.dumps(credentials, indent=2)
    )

    write_resume_pdf(
        Path("/app/src/harbor/resume_template.json"),
        email,
        args.output_dir / "alex_green_resume.pdf",
    )

    task = json.loads(args.task_json.read_text())
    for item in task.get("extra_info") or []:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        src = args.extra_info_dir / Path(item["path"]).name
        if src.is_file():
            shutil.copy2(src, args.output_dir / src.name)

    args.state_file.write_text(json.dumps({"email": email}, indent=2))
    print(f"Prepared ClawBench Harbor task data for {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
