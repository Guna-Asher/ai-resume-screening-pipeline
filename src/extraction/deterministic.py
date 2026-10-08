"""Rule-based resume parsing from pypdf text. No LLM. Simple section/entry heuristics.

Known limits (see README): multi-column layouts and unusual headings may parse poorly; when no
project/experience section is recognised the router falls back to the vision LLM.
"""
import re

from src.models import ExtractedExperience, ExtractedProject, ExtractedResume

_SECTION_NAMES = {
    "projects": ["projects", "personal projects", "academic projects", "selected projects", "key projects",
                 "technical projects", "side projects", "project experience", "notable projects"],
    "experience": ["experience", "work experience", "professional experience", "internships",
                   "internship experience", "internship", "employment", "employment history", "work history",
                   "relevant experience", "industry experience", "career history"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "skills and tools",
               "core competencies", "tools and technologies", "technical proficiencies"],
    "education": ["education", "academic background", "academics", "educational qualifications"],
    "other": ["summary", "profile", "objective", "career objective", "professional summary", "about me",
              "certifications", "certificates", "achievements", "awards", "honors", "publications",
              "extracurricular", "extracurricular activities", "positions of responsibility", "interests",
              "hobbies", "references", "links", "contact", "volunteering", "courses",
              "coursework", "leadership"],
}
SECTION_OF = {name: kind for kind, names in _SECTION_NAMES.items() for name in names}

_HEADING_WITH_CONTENT = re.compile(r"^\s*([A-Za-z &]{3,40}?)\s*[:\-]\s*(\S.*)$")
BULLET = re.compile(r"^\s*(?:[•●▪■◦○·*\-–—-]|\d{1,2}[.)])\s+")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", re.I)
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
TECH_LINE = re.compile(r"^\s*(?:tech(?:nologies)?(?: stack)?|stack|built with|tools|tech used)\s*[:\-]\s*(.+)$", re.I)
MAX_HEADER_CHARS = 120


def _heading_kind(line: str) -> str | None:
    key = re.sub(r"[^a-z& ]", "", line.lower()).replace("&", "and").strip()
    key = re.sub(r"\s+", " ", key)
    return SECTION_OF.get(key) if len(line) <= 40 else None


def _split_sections(lines: list[str]) -> tuple[list[str], dict[str, list[str]]]:
    header: list[str] = []
    sections: dict[str, list[str]] = {"projects": [], "experience": [], "skills": [], "education": [], "other": []}
    current: str | None = None
    for line in lines:
        kind = _heading_kind(line)
        if kind:
            current = kind
            continue
        m = _HEADING_WITH_CONTENT.match(line)
        if m and (kind := _heading_kind(m.group(1))):  # e.g. "Skills: Python, SQL"
            current = kind
            sections[kind].append(m.group(2))
            continue
        (sections[current] if current else header).append(line)
    return header, sections


def _looks_title_case(line: str) -> bool:
    words = re.findall(r"[A-Za-z][A-Za-z.+#-]*", line)
    return 0 < len(words) <= 8 and sum(w[0].isupper() for w in words) / len(words) >= 0.6


def _is_entry_header(line: str, prev: str, prev_blank: bool) -> bool:
    if len(line) > MAX_HEADER_CHARS or line[0].islower() or TECH_LINE.match(line):
        return False  # long prose, a wrapped continuation line, or a "Tech: ..." line
    cue = "|" in line or bool(YEAR.search(line)) or " – " in line or " — " in line or _looks_title_case(line)
    if line.endswith(".") and "|" not in line:
        return False
    return prev_blank or cue


def _split_entries(lines: list[str]) -> list[list[str]]:
    """Group a section's lines into entries: [header, body lines...]."""
    entries: list[list[str]] = []
    prev, prev_blank = "", True
    for raw in lines:
        line = raw.strip()
        if not line:
            prev_blank = True
            continue
        is_bullet = bool(BULLET.match(line))
        if not entries or (not is_bullet and _is_entry_header(line, prev, prev_blank)):
            entries.append([line])
        else:
            entries[-1].append(BULLET.sub("", line))
        prev, prev_blank = line, False
    return entries


def _split_tech(text: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,;|•/]", text) if 0 < len(t.strip()) <= 40]


def _parse_entry(entry: list[str]) -> tuple[str, list[str], str, list[str], list[str]]:
    """-> (header_first_part, header_rest_parts, description, technologies, evidence)"""
    header, body = entry[0], entry[1:]
    parts = [p.strip() for p in re.split(r"\s\|\s|\|", header) if p.strip()]
    technologies: list[str] = []
    description_lines: list[str] = []
    for line in body:
        m = TECH_LINE.match(line)
        if m:  # keep "Tech: ..." lines out of the description so "built with" is not read as a verb
            technologies += _split_tech(m.group(1))
        else:
            description_lines.append(line)
    evidence = [header, *description_lines[:2]]
    return parts[0] if parts else header, parts[1:], " ".join(description_lines), technologies, evidence


def _projects(lines: list[str]) -> list[ExtractedProject]:
    out = []
    for entry in _split_entries(lines):
        name, rest, desc, tech, evidence = _parse_entry(entry)
        tech += [t for part in rest if not YEAR.search(part) for t in _split_tech(part)]
        out.append(ExtractedProject(name=name, description=desc, technologies=tech, evidence=evidence))
    return out


def _experience(lines: list[str]) -> list[ExtractedExperience]:
    out = []
    for entry in _split_entries(lines):
        role, rest, desc, tech, evidence = _parse_entry(entry)
        company = next((p for p in rest if not YEAR.search(p)), "")
        out.append(ExtractedExperience(role=role, company=company, description=desc,
                                       technologies=tech, evidence=evidence))
    return out


def _skills(lines: list[str]) -> list[str]:
    skills: list[str] = []
    for line in lines:
        line = BULLET.sub("", line.strip())
        label, sep, rest = line.partition(":")
        if sep and len(label.split()) <= 3:  # "Languages: Python, Java"
            line = rest
        skills += [t.strip() for t in re.split(r"[,;|•]", line) if 0 < len(t.strip()) <= 40]
    return skills


def _name(header_lines: list[str]) -> str | None:
    for line in header_lines[:3]:
        line = line.strip()
        if line and len(line.split()) <= 6 and not re.search(r"[@\d]|https?://|github|linkedin", line, re.I):
            return line
    return None


def parse_resume_text(source_file: str, text: str) -> ExtractedResume:
    header, sections = _split_sections(text.splitlines())
    email = EMAIL.search(text)
    github = GITHUB.search(text)
    education = [BULLET.sub("", ln.strip()) for ln in sections["education"] if ln.strip()][:10]
    return ExtractedResume(
        source_file=source_file,
        name=_name([ln for ln in header if ln.strip()]),
        email=email.group(0) if email else None,
        github_url=github.group(0) if github else None,
        skills=_skills(sections["skills"]),
        projects=_projects(sections["projects"]),
        education=education,
        experience=_experience(sections["experience"]),
        raw_text=text,
        extraction_method="text",
    )
