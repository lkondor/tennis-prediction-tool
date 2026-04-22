import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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


COURT_NAMES = [
    "MANOLO SANTANA STADIUM",
    "ARANTXA SANCHEZ STADIUM",
    "STADIUM 3",
    "COURT 4",
    "COURT 5",
    "COURT 6",
    "COURT 7",
    "COURT 8",
]


NOISE_PATTERNS = [
    r"^\d+\.$",
    r"^\[\w+\]$",
    r"^ATP$",
    r"^WTA$",
    r"^SINGLES$",
    r"^DOUBLES$",
    r"^STARTS AT.*$",
    r"^FOLLOWED BY.*$",
    r"^NOT BEFORE.*$",
    r"^ORDER OF PLAY.*$",
    r"^MUTUA MADRID OPEN.*$",
    r"^ANY MATCH ON ANY COURT.*$",
    r"^ATP SINGLES ALTERNATE SIGN-IN DEADLINE.*$",
    r"^WTA SINGLES ALTERNATE SIGN-IN DEADLINE.*$",
    r"^TOURNAMENT DIRECTOR.*$",
    r"^RELEASED:.*$",
    r"^UMPIRE.*$",
    r"^REFEREE.*$",
    r"^SUPERVISOR.*$",
    r"^PAGE \d+.*$",
]


def _candidate_pdf_urls():
    """
    Cerca il PDF più recente attorno alla data odierna.
    Madrid pubblica normalmente Order of Play giornalieri in wp-content/uploads/YYYY/MM/OP-YYYY-MM-DD.pdf
    """
    today = datetime.now(timezone.utc).date()
    dates = []

    # prima date future/prossime, poi oggi, poi ieri e pochi giorni indietro
    for offset in [1, 0, -1, -2, -3, -4]:
        d = today + timedelta(days=offset)
        dates.append(d)

    urls = []
    for d in dates:
        urls.append(
            f"https://mutuamadridopen.com/wp-content/uploads/{d.year}/{d.month:02d}/OP-{d.year}-{d.month:02d}-{d.day:02d}.pdf"
        )
    return urls


def _download_pdf_text(url: str) -> str:
    if PdfReader is None:
        return ""

    try:
        r = requests.get(url, timeout=20)
        content_type = r.headers.get("content-type", "").lower()
        if r.status_code != 200 or "pdf" not in content_type:
            return ""

        reader = PdfReader(io.BytesIO(r.content))
        pages = []
        for page in reader.pages:
            txt = page.extract_text() or ""
            pages.append(txt)

        return "\n".join(pages)
    except Exception:
        return ""


def _normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text


def _clean_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"\[[^\]]+\]", "", line)  # [WC], [12], etc.
    line = re.sub(r"\([A-Z]{2,3}\)", "", line)  # (ESP), (ITA)
    line = re.sub(r"\s+", " ", line).strip(" -–•")
    return line.strip()


def _is_noise(line: str) -> bool:
    if not line:
        return True

    upper = line.upper().strip()

    for pattern in NOISE_PATTERNS:
        if re.match(pattern, upper):
            return True

    return False


def _looks_like_player_name(line: str) -> bool:
    if not line:
        return False

    if any(ch.isdigit() for ch in line):
        return False

    words = line.split()
    if len(words) < 2 or len(words) > 5:
        return False

    upper_words = [w.upper() for w in words]
    banned = {
        "MANOLO", "SANTANA", "ARANTXA", "SANCHEZ", "STADIUM", "COURT",
        "ORDER", "PLAY", "MADRID", "OPEN", "FOLLOWED", "STARTS",
        "TODAY", "TOMORROW"
    }
    if any(w in banned for w in upper_words):
        return False

    alpha_chars = [c for c in line if c.isalpha()]
    if not alpha_chars:
        return False

    upper_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
    return upper_ratio >= 0.55


def _split_by_courts(text: str):
    """
    Divide il testo per blocchi di campo.
    Ogni blocco parte da un nome campo ufficiale.
    """
    lines = [_clean_line(x) for x in _normalize_text(text).split("\n")]
    lines = [x for x in lines if x and not _is_noise(x)]

    blocks = []
    current_court = None
    current_lines = []

    for line in lines:
        upper = line.upper()
        if upper in COURT_NAMES:
            if current_court and current_lines:
                blocks.append((current_court.title(), current_lines))
            current_court = upper
            current_lines = []
        else:
            if current_court:
                current_lines.append(line)

    if current_court and current_lines:
        blocks.append((current_court.title(), current_lines))

    return blocks


def _extract_matches_from_court_block(court: str, lines: list[str]):
    matches = []
    candidates = []

    for line in lines:
        if _is_noise(line):
            continue

        if _looks_like_player_name(line):
            candidates.append(line.title())

            if len(candidates) == 2:
                p1, p2 = candidates[0], candidates[1]
                if p1 != p2:
                    matches.append(Match(p1, p2, court))
                candidates = []

        else:
            # resetta quando il flusso non sembra più coerente
            if candidates and len(candidates) == 1:
                # teniamo il primo se il secondo arriva subito dopo
                continue
            if len(candidates) > 2:
                candidates = []

    return matches


def _extract_matches_from_pdf_text(text: str):
    blocks = _split_by_courts(text)

    all_matches = []
    for court, lines in blocks:
        block_matches = _extract_matches_from_court_block(court, lines)
        all_matches.extend(block_matches)

    # dedup
    deduped = []
    seen = set()
    for m in all_matches:
        k1 = (m.player1.lower(), m.player2.lower(), m.court.lower())
        k2 = (m.player2.lower(), m.player1.lower(), m.court.lower())
        if k1 not in seen and k2 not in seen:
            seen.add(k1)
            deduped.append(m)

    return deduped


def _load_from_latest_official_pdf():
    for url in _candidate_pdf_urls():
        text = _download_pdf_text(url)
        if not text:
            continue

        matches = _extract_matches_from_pdf_text(text)
        if matches:
            return matches, url

    return [], None


def get_upcoming_matches():
    matches, source_url = _load_from_latest_official_pdf()
    if matches:
        return matches
    return DEMO_MATCHES


load_matches = get_upcoming_matches
