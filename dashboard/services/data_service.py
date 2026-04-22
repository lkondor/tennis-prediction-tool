import io
import re
from dataclasses import dataclass

import requests

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


@dataclass
class Match:
    player1: str
    player2: str
    court: str


DEMO_MATCHES = [
    Match("Sinner", "Medvedev", "Manolo Santana Stadium"),
    Match("Alcaraz", "Zverev", "Arantxa Sanchez Stadium"),
    Match("Swiatek", "Sabalenka", "Court 4"),
]


PDF_CANDIDATES = [
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-20.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-21.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-22.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-23.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-24.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-25.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-26.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-27.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-28.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-29.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/04/OP-2026-04-30.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/05/OP-2026-05-01.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/05/OP-2026-05-02.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/05/OP-2026-05-03.pdf",
    "https://mutuamadridopen.com/wp-content/uploads/2026/05/OP-2026-05-04.pdf",
]


COURT_NAMES = [
    "MANOLO SANTANA STADIUM",
    "ARANTXA SANCHEZ STADIUM",
    "COURT 3",
    "COURT 4",
    "COURT 5",
    "COURT 6",
    "COURT 7",
]


NOISE_PATTERNS = [
    r"\bSINGLES\b",
    r"\bDOUBLES\b",
    r"\bNOT BEFORE\b.*",
    r"\bFOLLOWED BY\b.*",
    r"\bSTARTING AT\b.*",
    r"\bORDER OF PLAY\b.*",
    r"\bMUTUA MADRID OPEN\b.*",
    r"\bATP\b",
    r"\bWTA\b",
    r"\bPRACTICE\b.*",
    r"\bWHEELCHAIR\b.*",
    r"\bUMPIRE\b.*",
    r"\bREFEREE\b.*",
    r"\bPage \d+\b",
    r"\bvs\.\b",
]


def _download_pdf_text(url: str) -> str:
    if PdfReader is None:
        return ""

    try:
        response = requests.get(url, timeout=20)
        if response.status_code != 200 or "application/pdf" not in response.headers.get("content-type", "").lower():
            return ""

        pdf_file = io.BytesIO(response.content)
        reader = PdfReader(pdf_file)

        text_parts = []
        for page in reader.pages:
            text = page.extract_text() or ""
            text_parts.append(text)

        return "\n".join(text_parts)
    except Exception:
        return ""


def _normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text


def _clean_line(line: str) -> str:
    line = line.strip()

    for pattern in NOISE_PATTERNS:
        line = re.sub(pattern, "", line, flags=re.IGNORECASE)

    line = re.sub(r"\[[^\]]*\]", "", line)
    line = re.sub(r"\([^\)]*\)", "", line)
    line = re.sub(r"\s+", " ", line).strip(" -–•")
    return line


def _looks_like_player_name(line: str) -> bool:
    if not line:
        return False

    if len(line) < 4 or len(line) > 40:
        return False

    if any(ch.isdigit() for ch in line):
        return False

    words = line.split()
    if len(words) < 2 or len(words) > 4:
        return False

    banned = {
        "STADIUM", "COURT", "ORDER", "PLAY", "MADRID", "OPEN", "SINGLES",
        "DOUBLES", "FOLLOWED", "STARTING", "MANOLO", "ARANTXA"
    }
    if any(word.upper() in banned for word in words):
        return False

    uppercase_ratio = sum(1 for c in line if c.isupper()) / max(1, sum(1 for c in line if c.isalpha()))
    return uppercase_ratio > 0.6


def _extract_matches_from_pdf_text(text: str):
    text = _normalize_text(text)
    raw_lines = text.split("\n")

    matches = []
    current_court = "Madrid"

    candidate_names = []

    for raw in raw_lines:
        line = _clean_line(raw)
        if not line:
            continue

        upper_line = line.upper()

        if upper_line in COURT_NAMES:
            current_court = line.title()
            candidate_names = []
            continue

        if _looks_like_player_name(upper_line):
            candidate_names.append(line.title())

            if len(candidate_names) >= 2:
                p1 = candidate_names[-2]
                p2 = candidate_names[-1]

                if p1 != p2:
                    matches.append(Match(p1, p2, current_court))

                candidate_names = []

    deduped = []
    seen = set()
    for m in matches:
        key = (m.player1.lower(), m.player2.lower(), m.court.lower())
        reverse_key = (m.player2.lower(), m.player1.lower(), m.court.lower())
        if key not in seen and reverse_key not in seen:
            seen.add(key)
            deduped.append(m)

    return deduped


def _load_from_official_pdf():
    for url in PDF_CANDIDATES:
        text = _download_pdf_text(url)
        if not text:
            continue

        matches = _extract_matches_from_pdf_text(text)
        if matches:
            return matches

    return []


def get_upcoming_matches():
    matches = _load_from_official_pdf()
    if matches:
        return matches
    return DEMO_MATCHES


load_matches = get_upcoming_matches
