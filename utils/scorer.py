"""Job scoring with technical role filtering — tuned for Active Jobs DB results."""

from typing import Dict, List

# ── Technical title keywords (ANY match → accept) ────────────────────
TECHNICAL_KEYWORDS = [
    'software', 'engineer', 'developer', 'programmer',
    'ml', 'machine learning', 'ai', 'data scientist',
    'backend', 'frontend', 'full stack', 'fullstack', 'full-stack',
    'platform', 'infrastructure', 'devops', 'sre', 'site reliability',
    'security engineer', 'research scientist', 'research engineer',
    'data engineer', 'analytics engineer', 'applied scientist',
    'computer vision', 'nlp', 'robotics', 'systems engineer',
    'cloud engineer', 'api engineer', 'automation engineer',
]

# ── Non-technical (ANY match in title → reject) ──────────────────────
NON_TECHNICAL_KEYWORDS = [
    'sales', 'account executive', 'business development', 'marketing',
    'recruiter', 'human resources', 'operations manager',
    'customer success', 'customer support', 'administrative',
    'finance', 'accounting', 'legal', 'compliance',
    'product manager', 'project manager', 'program manager',
    'mechanical engineer', 'civil engineer', 'electrical engineer',
    'nurse', 'physician', 'therapist', 'pharmacist',
]

# ── Senior-level keywords (title only → reject) ─────────────────────
SENIOR_KEYWORDS = [
    'senior', 'staff', 'principal', 'lead', 'director', 'vp ',
    'manager', 'head of', 'architect',
    '5+', '7+', '8+', '10+',
]


def is_technical_role(job_title: str) -> bool:
    """Check if job is a technical engineering role (not senior, not non-tech)."""
    t = job_title.lower()

    # Hard reject non-technical
    if any(kw in t for kw in NON_TECHNICAL_KEYWORDS):
        return False

    # Hard reject senior-level (unless explicitly "new grad" or "junior")
    has_junior = any(kw in t for kw in ['new grad', 'junior', 'entry', 'early career', 'associate', 'i ', ' i,', ' 1 ', ' 1,'])
    if not has_junior and any(kw in t for kw in SENIOR_KEYWORDS):
        return False

    # Accept if any technical keyword present
    if any(kw in t for kw in TECHNICAL_KEYWORDS):
        return True

    return False


class JobScorer:
    """Scores jobs 0-100 based on resume match, seniority, H-1B data, and company."""

    def __init__(self, resume_path: str = None):
        # Pavan's resume skills
        self.resume_skills = [
            'python', 'java', 'c++', 'javascript', 'sql', 'scala', 'kotlin', 'haskell',
            'tensorflow', 'pytorch', 'keras', 'ml', 'ai', 'machine learning',
            'flask', 'fastapi', 'django', 'react', 'node', 'spring',
            'aws', 'docker', 'kubernetes', 'postgresql', 'mongodb', 'redis',
            'kafka', 'nlp', 'llm', 'rag', 'langchain', 'hugging face',
            'data pipeline', 'etl', 'ci/cd', 'github actions',
            'linux', 'rest', 'api', 'microservice',
        ]

    def score_job(self, job: Dict, h1b_data: Dict = None) -> float:
        """
        Score 0-100:
          Base (10) — every technical role gets 10 free points
          Skill match (30)
          Role/seniority (25)
          H-1B history (20)
          Company tier (15)
        """
        if not is_technical_role(job.get('title', '')):
            return 0

        score = 10  # base points for passing the technical filter
        title = job.get('title', '').lower()
        desc  = job.get('description', '').lower()
        text  = title + ' ' + desc

        # ── 1. SKILL MATCH (max 30) ──────────────────────────
        matches = [s for s in self.resume_skills if s in text]
        n = len(matches)
        if   n >= 12: score += 30
        elif n >= 8:  score += 25
        elif n >= 5:  score += 20
        elif n >= 3:  score += 15
        elif n >= 1:  score += n * 5

        # ── 2. ROLE / SENIORITY (max 25) ─────────────────────
        if any(kw in title for kw in ['new grad', 'new graduate']):
            score += 25
        elif 'early career' in title:
            score += 22
        elif any(kw in title for kw in ['entry level', 'entry-level']):
            score += 22
        elif any(kw in title for kw in ['junior', 'jr.', 'jr ']):
            score += 18
        elif any(kw in title for kw in ['associate', ' i ', ' i,', ' 1 ']):
            score += 15
        elif any(kw in text for kw in ['0-2 years', '0-1 year', '1-2 years',
                                        'recent graduate', 'new grads',
                                        'entry level', 'early career']):
            score += 12
        else:
            # Generic SWE with no level indicator — still useful
            score += 5

        # ── 3. H-1B SPONSORSHIP (max 20) ─────────────────────
        if h1b_data:
            hires = h1b_data.get('New_Hires_Approved_2025', 0)
            if   hires >= 100: score += 12
            elif hires >= 50:  score += 16
            elif hires >= 20:  score += 20   # sweet spot
            elif hires >= 10:  score += 16
            elif hires >= 1:   score += 8

        # Bonus: description mentions sponsorship / visa
        if any(kw in text for kw in ['visa sponsorship', 'h-1b', 'h1b', 'sponsor']):
            score += 5

        # ── 4. COMPANY TIER (max 15) ─────────────────────────
        co = job.get('company', '').lower()
        if any(x in co for x in ['google', 'meta', 'amazon', 'apple', 'microsoft', 'netflix']):
            score += 15
        elif any(x in co for x in ['uber', 'linkedin', 'stripe', 'goldman', 'morgan stanley',
                                     'jpmorgan', 'bloomberg', 'citadel', 'two sigma']):
            score += 13
        elif any(x in co for x in ['openai', 'anthropic', 'databricks', 'snowflake',
                                     'notion', 'figma', 'datadog', 'coinbase', 'roblox']):
            score += 11
        else:
            score += 5

        return min(score, 100)

    def explain_score(self, job: Dict, score: float) -> str:
        """Human-readable score explanation."""
        if score == 0:
            return "Not a technical role"

        parts: List[str] = []
        text = (job.get('title', '') + ' ' + job.get('description', '')).lower()

        matched = [s for s in self.resume_skills if s in text]
        if matched:
            parts.append(f"✓ Skills ({len(matched)}): {', '.join(matched[:6])}")

        title = job.get('title', '').lower()
        if 'new grad' in title:
            parts.append("✓ New Grad role")
        elif 'early career' in title:
            parts.append("✓ Early Career")
        elif any(kw in title for kw in ['junior', 'entry']):
            parts.append("✓ Junior / Entry-Level")

        if any(kw in text for kw in ['visa sponsorship', 'h-1b', 'h1b', 'sponsor']):
            parts.append("✓ Mentions visa/sponsorship")

        parts.append(f"✓ Company: {job.get('company', 'Unknown')}")

        return "\n".join(parts) if parts else "Standard match"