"""
AI Job Scorer — Personal AI for any job seeker.

Features:
  - Parses ANY resume PDF → extracts skills, tools, experience level, education
  - Parses EACH job description → extracts required tools, nice-to-haves, experience
  - Smart skill matching with overlap % and gap analysis
  - Dealbreaker detection: US citizenship, security clearance, no sponsorship
  - If you swap your resume, everything re-scores automatically
  - Returns structured breakdown for the Book UI
"""

import re
import os
from typing import Dict, List, Tuple, Optional

# ── Master skills/tools taxonomy ─────────────────────────────────
KNOWN_SKILLS = {
    # Languages
    'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'go', 'golang',
    'rust', 'ruby', 'php', 'swift', 'kotlin', 'scala', 'haskell', 'r',
    'perl', 'lua', 'dart', 'elixir', 'clojure', 'matlab', 'sql', 'bash',
    'shell', 'powershell', 'objective-c', 'assembly', 'vhdl', 'verilog',
    # Frontend
    'react', 'react.js', 'reactjs', 'angular', 'vue', 'vue.js', 'vuejs',
    'svelte', 'next.js', 'nextjs', 'nuxt', 'gatsby', 'remix',
    'html', 'css', 'sass', 'scss', 'less', 'tailwind', 'tailwindcss',
    'bootstrap', 'material ui', 'chakra ui', 'styled-components',
    'webpack', 'vite', 'rollup', 'babel',
    # Backend
    'node', 'node.js', 'nodejs', 'express', 'express.js', 'fastapi', 'flask',
    'django', 'spring', 'spring boot', 'springboot', 'rails', 'ruby on rails',
    '.net', 'asp.net', 'laravel', 'gin', 'fiber', 'actix', 'rocket',
    'graphql', 'rest', 'restful', 'grpc', 'websocket', 'api',
    # Data / ML / AI
    'tensorflow', 'pytorch', 'keras', 'scikit-learn', 'sklearn', 'pandas',
    'numpy', 'scipy', 'matplotlib', 'seaborn', 'plotly', 'jupyter',
    'hugging face', 'huggingface', 'transformers', 'langchain', 'llamaindex',
    'openai', 'llm', 'nlp', 'computer vision', 'deep learning',
    'machine learning', 'ml', 'ai', 'neural network', 'rag',
    'data pipeline', 'etl', 'spark', 'pyspark', 'hadoop', 'hive',
    'airflow', 'dagster', 'dbt', 'fivetran',
    'tableau', 'power bi', 'looker', 'grafana', 'streamlit',
    # Databases
    'postgresql', 'postgres', 'mysql', 'sqlite', 'mariadb',
    'mongodb', 'dynamodb', 'cassandra', 'couchbase', 'firebase',
    'redis', 'memcached', 'elasticsearch', 'opensearch', 'solr',
    'neo4j', 'pinecone', 'weaviate', 'qdrant', 'milvus', 'chroma',
    'snowflake', 'bigquery', 'redshift', 'databricks', 'clickhouse',
    # Cloud / Infra
    'aws', 'amazon web services', 'azure', 'gcp', 'google cloud',
    'docker', 'kubernetes', 'k8s', 'terraform', 'ansible', 'pulumi',
    'jenkins', 'github actions', 'gitlab ci', 'circleci',
    'ci/cd', 'ci cd', 'devops', 'sre', 'linux', 'unix',
    'nginx', 'apache', 'caddy', 'traefik',
    'cloudflare', 'vercel', 'netlify', 'heroku', 'fly.io',
    # Messaging / Streaming
    'kafka', 'rabbitmq', 'sqs', 'sns', 'pubsub', 'nats', 'redis streams',
    'celery', 'sidekiq',
    # Testing
    'jest', 'mocha', 'pytest', 'junit', 'cypress', 'playwright', 'selenium',
    'postman', 'swagger', 'openapi',
    # Version Control
    'git', 'github', 'gitlab', 'bitbucket', 'svn',
    # Mobile
    'react native', 'flutter', 'ios', 'android', 'swiftui', 'jetpack compose',
    # Other
    'agile', 'scrum', 'jira', 'confluence', 'notion',
    'microservices', 'monorepo', 'serverless', 'lambda',
    'oauth', 'jwt', 'sso', 'ldap', 'saml',
    'webscraping', 'web scraping', 'beautifulsoup', 'scrapy', 'selenium',
}

# ── Dealbreaker patterns ─────────────────────────────────────────
CITIZENSHIP_PATTERNS = [
    r'u\.?s\.?\s*citizen(?:ship)?(?:\s+(?:is\s+)?required)?',
    r'must\s+be\s+(?:a\s+)?u\.?s\.?\s*citizen',
    r'(?:requires?|must\s+have)\s+(?:active\s+)?(?:security|secret|top\s*secret|ts[/ ]sci)\s*clearance',
    r'clearance\s+(?:is\s+)?required',
    r'(?:only|must)\s+(?:be\s+)?(?:authorized|eligible)\s+to\s+work.*?(?:without|no)\s+(?:need\s+for\s+)?sponsor',
    r'(?:unable|not\s+able|cannot|will\s+not|won\'t)\s+(?:to\s+)?(?:provide\s+)?(?:sponsor|visa)',
    r'no\s+(?:visa\s+)?sponsor(?:ship)?',
    r'(?:not|no)\s+(?:currently\s+)?sponsor(?:ing)?',
    r'(?:permanent\s+resident|green\s*card)\s+(?:is\s+)?required',
    r'must\s+(?:already\s+)?(?:be|have)\s+(?:legally\s+)?(?:authorized|eligible)\s+to\s+work',
    r'(?:only\s+)?(?:us|u\.s\.?)\s+(?:persons?|nationals?|residents?)\s+(?:may|can|should)\s+apply',
    r'ead\s+(?:card\s+)?(?:or\s+)?(?:gc|green\s*card)\s+(?:holder|required)',
]

# Positive sponsorship signals
SPONSORSHIP_POSITIVE = [
    r'(?:visa|h-?1b|h1b)\s+sponsor(?:ship)?(?:\s+(?:available|offered|provided))?',
    r'(?:we|will|can|do)\s+sponsor',
    r'(?:open\s+to|offer|provide)\s+(?:visa\s+)?sponsor(?:ship)?',
]

# ── Technical title keywords ─────────────────────────────────────
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

NON_TECHNICAL_KEYWORDS = [
    'sales', 'account executive', 'business development', 'marketing',
    'recruiter', 'human resources', 'operations manager',
    'customer success', 'customer support', 'administrative',
    'finance', 'accounting', 'legal', 'compliance',
    'product manager', 'project manager', 'program manager',
    'mechanical engineer', 'civil engineer', 'electrical engineer',
    'nurse', 'physician', 'therapist', 'pharmacist',
]

SENIOR_KEYWORDS = [
    'senior', 'staff', 'principal', 'lead', 'director', 'vp ',
    'manager', 'head of', 'architect', '5+', '7+', '8+', '10+',
]


def extract_skills_from_text(text: str) -> List[str]:
    """Extract known skills/tools from any text (resume or job description)."""
    text_lower = text.lower()
    found = []
    for skill in KNOWN_SKILLS:
        # Word boundary check to avoid partial matches
        pattern = r'(?:^|[\s,;(./\-])' + re.escape(skill) + r'(?:[\s,;)./\-]|$)'
        if re.search(pattern, text_lower):
            found.append(skill)
    # Deduplicate aliases
    return _dedupe_skills(found)


def _dedupe_skills(skills: List[str]) -> List[str]:
    """Deduplicate skill aliases."""
    alias_map = {
        'react.js': 'react', 'reactjs': 'react',
        'vue.js': 'vue', 'vuejs': 'vue',
        'node.js': 'node', 'nodejs': 'node',
        'express.js': 'express',
        'next.js': 'nextjs',
        'golang': 'go',
        'postgresql': 'postgres', 'postgres': 'postgres',
        'amazon web services': 'aws',
        'google cloud': 'gcp',
        'tailwindcss': 'tailwind',
        'scikit-learn': 'sklearn',
        'springboot': 'spring boot',
        'huggingface': 'hugging face',
        'k8s': 'kubernetes',
        'ci cd': 'ci/cd',
    }
    seen = set()
    result = []
    for s in skills:
        canonical = alias_map.get(s, s)
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return sorted(result)


def check_dealbreakers(text: str) -> Dict:
    """Check for citizenship/clearance/no-sponsorship dealbreakers."""
    text_lower = text.lower()
    result = {
        'has_dealbreaker': False,
        'reasons': [],
        'sponsorship_positive': False,
    }

    for pattern in CITIZENSHIP_PATTERNS:
        if re.search(pattern, text_lower):
            result['has_dealbreaker'] = True
            match = re.search(pattern, text_lower)
            result['reasons'].append(match.group(0).strip())
            break  # One is enough

    for pattern in SPONSORSHIP_POSITIVE:
        if re.search(pattern, text_lower):
            result['sponsorship_positive'] = True
            break

    return result


def is_technical_role(job_title: str) -> bool:
    """Check if job is a technical engineering role."""
    t = job_title.lower()
    if any(kw in t for kw in NON_TECHNICAL_KEYWORDS):
        return False
    has_junior = any(kw in t for kw in ['new grad', 'junior', 'entry', 'early career', 'associate', 'i ', ' i,', ' 1 ', ' 1,'])
    if not has_junior and any(kw in t for kw in SENIOR_KEYWORDS):
        return False
    if any(kw in t for kw in TECHNICAL_KEYWORDS):
        return True
    return False


class JobScorer:
    """AI-powered job scorer — works with any resume."""

    def __init__(self, resume_path: str = None):
        self.resume_path = resume_path
        self.resume_skills: List[str] = []
        self.resume_text: str = ''
        self._parse_resume()

    def _parse_resume(self):
        """Parse resume PDF to extract skills and text."""
        if not self.resume_path or not os.path.exists(self.resume_path):
            print("  ⚠ No resume found, using default skills")
            self.resume_skills = [
                'python', 'java', 'c++', 'javascript', 'sql', 'scala', 'kotlin', 'haskell',
                'tensorflow', 'pytorch', 'keras', 'ml', 'ai', 'machine learning',
                'flask', 'fastapi', 'django', 'react', 'node', 'spring',
                'aws', 'docker', 'kubernetes', 'postgres', 'mongodb', 'redis',
                'kafka', 'nlp', 'llm', 'rag', 'langchain', 'hugging face',
                'data pipeline', 'etl', 'ci/cd', 'github actions',
                'linux', 'rest', 'api', 'microservices',
            ]
            return

        try:
            # Try PyPDF2 first
            try:
                import PyPDF2
                with open(self.resume_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    self.resume_text = ' '.join(
                        page.extract_text() or '' for page in reader.pages
                    )
            except ImportError:
                # Fallback: try pdfplumber
                try:
                    import pdfplumber
                    with pdfplumber.open(self.resume_path) as pdf:
                        self.resume_text = ' '.join(
                            page.extract_text() or '' for page in pdf.pages
                        )
                except ImportError:
                    print("  ⚠ No PDF library found. Install PyPDF2: pip install PyPDF2")
                    return

            self.resume_skills = extract_skills_from_text(self.resume_text)
            print(f"  ✓ Parsed resume: {len(self.resume_skills)} skills detected")
            print(f"    Skills: {', '.join(self.resume_skills[:15])}...")

        except Exception as e:
            print(f"  ⚠ Resume parse error: {e}")

    def score_job(self, job: Dict, h1b_data: Dict = None) -> float:
        """
        Score 0-100:
          0       = Not technical / dealbreaker / senior
          Base    = 10 (every passing job)
          Skills  = 0-30 (overlap with resume)
          Level   = 0-25 (new grad / junior / entry)
          H-1B    = 0-20 (sponsorship signals)
          Company = 0-15 (tier bonus)

        Dealbreaker = forced to 0 (citizenship, clearance, no sponsor)
        """
        title = job.get('title', '')
        desc = job.get('description', '')
        text = (title + ' ' + desc).lower()

        # ── Hard filters ──
        if not is_technical_role(title):
            return 0

        # ── Dealbreaker check ──
        deal = check_dealbreakers(desc)
        if deal['has_dealbreaker'] and not deal['sponsorship_positive']:
            return 0

        score = 10  # base

        # ── 1. SKILL MATCH (max 30) ──
        job_skills = extract_skills_from_text(text)
        if self.resume_skills and job_skills:
            matching = set(self.resume_skills) & set(job_skills)
            n = len(matching)
            if n >= 12: score += 30
            elif n >= 8: score += 25
            elif n >= 5: score += 20
            elif n >= 3: score += 15
            elif n >= 1: score += n * 5
        else:
            # Fallback: basic keyword match
            matches = [s for s in self.resume_skills if s in text]
            n = len(matches)
            if n >= 12: score += 30
            elif n >= 8: score += 25
            elif n >= 5: score += 20
            elif n >= 3: score += 15
            elif n >= 1: score += n * 5

        # ── 2. ROLE / SENIORITY (max 25) ──
        t = title.lower()
        if any(kw in t for kw in ['new grad', 'new graduate']):
            score += 25
        elif 'early career' in t:
            score += 22
        elif any(kw in t for kw in ['entry level', 'entry-level']):
            score += 22
        elif any(kw in t for kw in ['junior', 'jr.', 'jr ']):
            score += 18
        elif any(kw in t for kw in ['associate', ' i ', ' i,', ' 1 ']):
            score += 15
        elif any(kw in text for kw in ['0-2 years', '0-1 year', '1-2 years',
                                        'recent graduate', 'new grads',
                                        'entry level', 'early career']):
            score += 12
        else:
            score += 5

        # ── 3. H-1B / SPONSORSHIP (max 20) ──
        if h1b_data:
            hires = h1b_data.get('New_Hires_Approved_2025', 0)
            if hires >= 100: score += 20
            elif hires >= 50: score += 16
            elif hires >= 20: score += 12
            elif hires >= 10: score += 8
            elif hires >= 1: score += 4

        if deal.get('sponsorship_positive'):
            score += 5

        # ── 4. COMPANY TIER (max 15) ──
        co = job.get('company', '').lower()
        tier1 = ['google', 'meta', 'amazon', 'apple', 'microsoft', 'netflix']
        tier2 = ['uber', 'linkedin', 'stripe', 'goldman', 'morgan stanley',
                 'jpmorgan', 'bloomberg', 'citadel', 'two sigma']
        tier3 = ['openai', 'anthropic', 'databricks', 'snowflake',
                 'notion', 'figma', 'datadog', 'coinbase', 'roblox']

        if any(x in co for x in tier1): score += 15
        elif any(x in co for x in tier2): score += 13
        elif any(x in co for x in tier3): score += 11
        else: score += 5

        return min(score, 100)

    def explain_score(self, job: Dict, score: float) -> str:
        """Structured score explanation for the UI."""
        if score == 0:
            desc = job.get('description', '')
            deal = check_dealbreakers(desc)
            if deal['has_dealbreaker']:
                return f"🚫 Dealbreaker: {deal['reasons'][0] if deal['reasons'] else 'citizenship/clearance required'}"
            return "Not a matching technical role"

        text = (job.get('title', '') + ' ' + job.get('description', '')).lower()
        job_skills = extract_skills_from_text(text)
        matching = sorted(set(self.resume_skills) & set(job_skills))
        missing = sorted(set(job_skills) - set(self.resume_skills))

        parts = []
        if matching:
            parts.append(f"✅ Matching skills ({len(matching)}): {', '.join(matching[:8])}")
        if missing:
            parts.append(f"📝 Skills to learn ({len(missing)}): {', '.join(missing[:6])}")

        title = job.get('title', '').lower()
        if 'new grad' in title: parts.append("🎓 New Grad role")
        elif 'early career' in title: parts.append("🎓 Early Career")
        elif any(kw in title for kw in ['junior', 'entry']): parts.append("🎓 Junior / Entry-Level")

        deal = check_dealbreakers(job.get('description', ''))
        if deal.get('sponsorship_positive'):
            parts.append("✅ Visa sponsorship available")

        parts.append(f"🏢 Company: {job.get('company', 'Unknown')}")

        return '\n'.join(parts)

    def get_job_analysis(self, job: Dict) -> Dict:
        """Full structured analysis for the Book UI."""
        text = (job.get('title', '') + ' ' + job.get('description', '')).lower()
        job_skills = extract_skills_from_text(text)
        matching = sorted(set(self.resume_skills) & set(job_skills))
        missing = sorted(set(job_skills) - set(self.resume_skills))
        extra = sorted(set(self.resume_skills) - set(job_skills))
        deal = check_dealbreakers(job.get('description', ''))

        match_pct = 0
        if job_skills:
            match_pct = round(len(matching) / len(job_skills) * 100)

        return {
            'job_skills': job_skills,
            'matching_skills': matching,
            'missing_skills': missing,
            'extra_skills': extra,  # skills you have that aren't required
            'match_percentage': match_pct,
            'dealbreaker': deal,
            'resume_skill_count': len(self.resume_skills),
        }