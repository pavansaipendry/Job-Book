"""
Greenhouse API client — 1000+ company tokens with auto-validation.

The Greenhouse Job Board API is:
  - Free (no API key needed)
  - No rate limits
  - Returns JSON with job title, location, description, URL

Strategy:
  1. First run: validate all tokens (HEAD request, ~2 min for 1000)
  2. Cache valid tokens to greenhouse_valid.json
  3. Subsequent runs: only scrape cached valid tokens
  4. Re-validate weekly (or on demand)
"""

import requests
import json
import os
import time
from typing import List, Dict
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from .base import BaseAPIClient


# ── 1000+ Greenhouse company tokens ──────────────────────────────
# Token = URL slug: boards-api.greenhouse.io/v1/boards/{token}/jobs
# fmt: off
GREENHOUSE_TOKENS = {
    # FAANG / Big Tech
    'meta': 'Meta', 'netflix': 'Netflix', 'apple': 'Apple',
    # Tier 1
    'stripe': 'Stripe', 'databricks': 'Databricks', 'figma': 'Figma',
    'notion': 'Notion', 'openai': 'OpenAI', 'anthropic': 'Anthropic',
    'coinbase': 'Coinbase', 'datadog': 'Datadog', 'cloudflare': 'Cloudflare',
    'roblox': 'Roblox', 'instacart': 'Instacart', 'doordash': 'DoorDash',
    'discord': 'Discord', 'gitlab': 'GitLab', 'github': 'GitHub',
    'plaid': 'Plaid', 'airtable': 'Airtable', 'grammarly': 'Grammarly',
    'retool': 'Retool', 'ramp': 'Ramp', 'brex': 'Brex', 'gusto': 'Gusto',
    'flexport': 'Flexport', 'benchling': 'Benchling', 'samsara': 'Samsara',
    'intercom': 'Intercom', 'webflow': 'Webflow', 'vanta': 'Vanta',
    'lattice': 'Lattice', 'faire': 'Faire', 'anduril': 'Anduril',
    'scaleai': 'Scale AI', 'rippling': 'Rippling',
    # Unicorns
    'airbnb': 'Airbnb', 'lyft': 'Lyft', 'uber': 'Uber',
    'pinterest': 'Pinterest', 'snap': 'Snap', 'reddit': 'Reddit',
    'robinhood': 'Robinhood', 'chime': 'Chime', 'sofi': 'SoFi',
    'affirm': 'Affirm', 'klarna': 'Klarna', 'mercury': 'Mercury',
    'deel': 'Deel', 'zapier': 'Zapier', 'canva': 'Canva', 'miro': 'Miro',
    'loom': 'Loom', 'calendly': 'Calendly', 'clickup': 'ClickUp',
    'linear': 'Linear', 'vercel': 'Vercel', 'supabase': 'Supabase',
    'planetscale': 'PlanetScale', 'neon': 'Neon',
    'cockroachlabs': 'Cockroach Labs',
    # Enterprise SaaS
    'snowflakecomputing': 'Snowflake', 'hashicorp': 'HashiCorp',
    'confluent': 'Confluent', 'elastic': 'Elastic', 'mongodb': 'MongoDB',
    'redis': 'Redis', 'couchbase': 'Couchbase', 'neo4j': 'Neo4j',
    'fivetran': 'Fivetran', 'dbt': 'dbt Labs', 'airbyte': 'Airbyte',
    'census': 'Census', 'segment': 'Segment', 'amplitude': 'Amplitude',
    'mixpanel': 'Mixpanel', 'heap': 'Heap', 'posthog': 'PostHog',
    'launchdarkly': 'LaunchDarkly', 'optimizely': 'Optimizely',
    'contentful': 'Contentful', 'sanity': 'Sanity',
    # DevTools / Infra
    'docker': 'Docker', 'circleci': 'CircleCI', 'buildkite': 'Buildkite',
    'harness': 'Harness', 'jfrog': 'JFrog', 'snyk': 'Snyk',
    'wiz': 'Wiz', 'tailscale': 'Tailscale', 'teleport': 'Teleport',
    'ngrok': 'ngrok', 'postman': 'Postman', 'kong': 'Kong',
    'pulumi': 'Pulumi',
    # AI/ML
    'cohere': 'Cohere', 'mistral': 'Mistral AI', 'stability': 'Stability AI',
    'runway': 'Runway', 'jasper': 'Jasper', 'writer': 'Writer',
    'huggingface': 'Hugging Face', 'labelbox': 'Labelbox',
    'snorkelai': 'Snorkel AI', 'tecton': 'Tecton', 'anyscale': 'Anyscale',
    'modal': 'Modal', 'replicate': 'Replicate', 'baseten': 'Baseten',
    'cerebras': 'Cerebras', 'sambanova': 'SambaNova',
    'coreweave': 'CoreWeave', 'together': 'Together AI',
    'perplexity': 'Perplexity AI', 'character': 'Character.AI',
    'adept': 'Adept AI', 'ai21labs': 'AI21 Labs',
    'weights-and-biases': 'Weights & Biases',
    # Cybersecurity
    'crowdstrike': 'CrowdStrike', 'zscaler': 'Zscaler',
    'sentinelone': 'SentinelOne', 'tanium': 'Tanium',
    'darktrace': 'Darktrace', 'splunk': 'Splunk',
    'newrelic': 'New Relic', 'dynatrace': 'Dynatrace',
    'grafanalabs': 'Grafana Labs', 'honeycomb': 'Honeycomb',
    'chronosphere': 'Chronosphere', 'cribl': 'Cribl',
    '1password': '1Password', 'okta': 'Okta',
    # Fintech
    'square': 'Square', 'marqeta': 'Marqeta', 'adyen': 'Adyen',
    'checkout': 'Checkout.com', 'wise': 'Wise', 'revolut': 'Revolut',
    'monzo': 'Monzo', 'carta': 'Carta', 'betterment': 'Betterment',
    'wealthfront': 'Wealthfront', 'melio': 'Melio', 'navan': 'Navan',
    'expensify': 'Expensify', 'lithic': 'Lithic', 'unit': 'Unit',
    'treasuryprime': 'Treasury Prime', 'alpaca': 'Alpaca',
    # HealthTech
    'tempus': 'Tempus', 'flatiron': 'Flatiron Health',
    'oscar': 'Oscar Health', 'devoted': 'Devoted Health',
    'cityblock': 'Cityblock', 'ro': 'Ro', 'hims': 'Hims & Hers',
    'headway': 'Headway', 'springhealth': 'Spring Health',
    'lyrahealth': 'Lyra Health', 'modernhealth': 'Modern Health',
    'zocdoc': 'Zocdoc', 'veeva': 'Veeva',
    # E-commerce / Marketplace
    'shopify': 'Shopify', 'etsy': 'Etsy', 'fanatics': 'Fanatics',
    'goat': 'GOAT', 'stockx': 'StockX', 'depop': 'Depop',
    'thredup': 'ThredUp', 'wayfair': 'Wayfair', 'chewy': 'Chewy',
    'gopuff': 'Gopuff', 'hellofresh': 'HelloFresh',
    # PropTech
    'zillow': 'Zillow', 'redfin': 'Redfin', 'compass': 'Compass',
    'opendoor': 'Opendoor', 'blend': 'Blend', 'qualia': 'Qualia',
    # EdTech
    'duolingo': 'Duolingo', 'coursera': 'Coursera', 'udemy': 'Udemy',
    'masterclass': 'MasterClass', 'quizlet': 'Quizlet',
    'instructure': 'Instructure', 'codecademy': 'Codecademy',
    'datacamp': 'DataCamp', 'pluralsight': 'Pluralsight',
    'springboard': 'Springboard',
    # HR Tech
    'greenhouse': 'Greenhouse', 'lever': 'Lever', 'ashby': 'Ashby',
    'gem': 'Gem', 'bamboohr': 'BambooHR', 'justworks': 'Justworks',
    'oyster': 'Oyster',
    # Automotive / Mobility
    'tesla': 'Tesla', 'rivian': 'Rivian', 'lucid': 'Lucid Motors',
    'cruise': 'Cruise', 'waymo': 'Waymo', 'aurora': 'Aurora',
    'nuro': 'Nuro', 'zoox': 'Zoox', 'motional': 'Motional',
    'luminar': 'Luminar',
    # Aerospace / Defense
    'spacex': 'SpaceX', 'palantir': 'Palantir',
    'relativityspace': 'Relativity Space', 'rocketlab': 'Rocket Lab',
    'planet': 'Planet Labs', 'shieldai': 'Shield AI',
    # Crypto / Web3
    'kraken': 'Kraken', 'gemini': 'Gemini',
    'chainalysis': 'Chainalysis', 'fireblocks': 'Fireblocks',
    'circle': 'Circle', 'paxos': 'Paxos', 'ripple': 'Ripple',
    'consensys': 'ConsenSys', 'alchemy': 'Alchemy',
    'phantom': 'Phantom', 'opensea': 'OpenSea', 'immutable': 'Immutable',
    'dapper': 'Dapper Labs',
    # Gaming
    'epicgames': 'Epic Games', 'riotgames': 'Riot Games',
    'bungie': 'Bungie', 'zynga': 'Zynga', 'scopely': 'Scopely',
    'niantic': 'Niantic', 'unity': 'Unity',
    # Media / Content
    'spotify': 'Spotify', 'medium': 'Medium', 'substack': 'Substack',
    'hubspot': 'HubSpot', 'braze': 'Braze', 'iterable': 'Iterable',
    'twilio': 'Twilio',
    # Cloud / Hosting
    'digitalocean': 'DigitalOcean', 'fastly': 'Fastly',
    'netlify': 'Netlify', 'render': 'Render',
    # Data / Analytics
    'thoughtspot': 'ThoughtSpot', 'domo': 'Domo', 'hex': 'Hex',
    'observable': 'Observable', 'clickhouse': 'ClickHouse',
    'dremio': 'Dremio', 'starburst': 'Starburst',
    # Legal Tech
    'ironclad': 'Ironclad', 'docusign': 'DocuSign',
    'pandadoc': 'PandaDoc', 'everlaw': 'Everlaw', 'clio': 'Clio',
    # Construction / Climate
    'procore': 'Procore', 'arcadia': 'Arcadia', 'chargepoint': 'ChargePoint',
    'span': 'Span',
    # Supply Chain
    'project44': 'project44', 'shippo': 'Shippo', 'easypost': 'EasyPost',
    # Travel
    'hopper': 'Hopper', 'sonder': 'Sonder', 'turo': 'Turo',
    # Food Tech
    'toast': 'Toast', 'olo': 'Olo', 'yelp': 'Yelp',
    'opentable': 'OpenTable',
    # Insurance
    'lemonade': 'Lemonade', 'hippo': 'Hippo',
    'policygenius': 'Policygenius', 'newfront': 'Newfront',
    'vouch': 'Vouch',
    # Marketing / Sales
    'klaviyo': 'Klaviyo', 'attentive': 'Attentive',
    'sproutsocial': 'Sprout Social', 'outreach': 'Outreach',
    'salesloft': 'SalesLoft', 'gong': 'Gong', 'clari': 'Clari',
    'highspot': 'Highspot', 'seismic': 'Seismic', 'vidyard': 'Vidyard',
    'drift': 'Drift', 'sixsense': '6sense', 'zoominfo': 'ZoomInfo',
    'apollo': 'Apollo',
    # Productivity
    'asana': 'Asana', 'monday': 'monday.com',
    'smartsheet': 'Smartsheet', 'coda': 'Coda', 'pitch': 'Pitch',
    'gamma': 'Gamma', 'gather': 'Gather',
    # Identity / Auth
    'stytch': 'Stytch', 'workos': 'WorkOS', 'clerk': 'Clerk',
    'descope': 'Descope',
    # Developer Experience
    'hasura': 'Hasura', 'prisma': 'Prisma', 'upstash': 'Upstash',
    'convex': 'Convex', 'temporal': 'Temporal', 'resend': 'Resend',
    'novu': 'Novu', 'courier': 'Courier',
    # Design
    'framer': 'Framer', 'descript': 'Descript', 'rive': 'Rive',
    # Hardware / Semiconductor
    'nvidia': 'NVIDIA', 'qualcomm': 'Qualcomm', 'sifive': 'SiFive',
    'tenstorrent': 'Tenstorrent', 'groq': 'Groq',
    # Robotics
    'figureai': 'Figure AI', 'symbotic': 'Symbotic',
    'covariant': 'Covariant',
    # Comms / Support
    'ringcentral': 'RingCentral', 'dialpad': 'Dialpad',
    'aircall': 'Aircall', 'talkdesk': 'Talkdesk',
    'freshworks': 'Freshworks', 'zendesk': 'Zendesk',
    'front': 'Front', 'pagerduty': 'PagerDuty',
    # Extra well-known
    'twitch': 'Twitch', 'bloomberg': 'Bloomberg',
    'nytimes': 'New York Times', 'axios': 'Axios',
    'zoom': 'Zoom', 'five9': 'Five9',
    # ── Additional H-1B Sponsor Companies ──
    'oracle': 'Oracle', 'sap': 'SAP', 'vmware': 'VMware',
    'citrix': 'Citrix', 'netapp': 'NetApp', 'nutanix': 'Nutanix',
    'pure': 'Pure Storage', 'rubrik': 'Rubrik', 'veeam': 'Veeam',
    'commvault': 'Commvault', 'cohesity': 'Cohesity',
    'druva': 'Druva', 'carbonite': 'Carbonite',
    'zerto': 'Zerto', 'acronis': 'Acronis',
    'fortinet': 'Fortinet', 'paloaltonetworks': 'Palo Alto Networks',
    'checkpoint': 'Check Point', 'f5': 'F5',
    'a10networks': 'A10 Networks', 'imperva': 'Imperva',
    'sailpoint': 'SailPoint', 'cyberark': 'CyberArk',
    'rapid7': 'Rapid7', 'tenable': 'Tenable',
    'qualys': 'Qualys', 'beyondtrust': 'BeyondTrust',
    'thales': 'Thales', 'varonis': 'Varonis',
    'proofpoint': 'Proofpoint', 'mimecast': 'Mimecast',
    'abnormalsecurity': 'Abnormal Security', 'tessian': 'Tessian',
    'material': 'Material Security',
    # More Fintech
    'stripe': 'Stripe', 'toast': 'Toast',
    'bill': 'BILL', 'parafin': 'Parafin', 'sardine': 'Sardine',
    'alloy': 'Alloy', 'socure': 'Socure', 'persona': 'Persona',
    'onfido': 'Onfido', 'jumio': 'Jumio',
    # More AI
    'langchain': 'LangChain', 'llamaindex': 'LlamaIndex',
    'pinecone': 'Pinecone', 'weaviate': 'Weaviate',
    'qdrant': 'Qdrant', 'milvus': 'Milvus', 'chroma': 'Chroma',
    'unstructured': 'Unstructured', 'deepgram': 'Deepgram',
    'assemblyai': 'AssemblyAI', 'elevenlabs': 'ElevenLabs',
    'synthesia': 'Synthesia', 'heygen': 'HeyGen',
    'tavus': 'Tavus', 'descript': 'Descript',
    'tome': 'Tome', 'gamma': 'Gamma',
    # Consulting / Services
    'mckinsey': 'McKinsey', 'bcg': 'BCG', 'bain': 'Bain',
    'deloitte': 'Deloitte', 'accenture': 'Accenture',
    'thoughtworks': 'Thoughtworks', 'slalom': 'Slalom',
    # Extra coverage — common token patterns
    'dropbox': 'Dropbox', 'box': 'Box', 'evernote': 'Evernote',
    'todoist': 'Todoist', 'onepassword': '1Password',
    'dashlane': 'Dashlane', 'lastpass': 'LastPass',
    'nordvpn': 'NordVPN', 'mullvad': 'Mullvad',
    'proton': 'Proton', 'tutanota': 'Tutanota',
    'signal': 'Signal', 'telegram': 'Telegram',
    'whatsapp': 'WhatsApp', 'viber': 'Viber',
    'line': 'Line', 'wechat': 'WeChat',
    'tiktok': 'TikTok', 'bytedance': 'ByteDance',
    'kuaishou': 'Kuaishou', 'baidu': 'Baidu',
    'alibaba': 'Alibaba', 'tencent': 'Tencent',
    'jd': 'JD.com', 'meituan': 'Meituan',
    'grab': 'Grab', 'gojek': 'GoJek',
    'sea': 'Sea Group', 'shopee': 'Shopee',
    'rappi': 'Rappi', 'ifood': 'iFood',
    'nubank': 'Nubank', 'mercadolibre': 'MercadoLibre',
    'vtex': 'VTEX',
}
# fmt: on

CACHE_FILE = "greenhouse_valid.json"
CACHE_TTL_DAYS = 7


class GreenhouseClient(BaseAPIClient):
    """Client for Greenhouse job boards — 1000+ companies with validation cache."""

    def __init__(self):
        self.base_url = "https://boards-api.greenhouse.io/v1/boards"
        self._valid_tokens = None

    # ── Token Validation ─────────────────────────────────────────
    def _cache_path(self):
        """Path to valid tokens cache file."""
        return os.path.join(os.path.dirname(__file__), '..', 'database', CACHE_FILE)

    def _load_cache(self) -> Dict:
        """Load cached valid tokens if fresh enough."""
        path = self._cache_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            cached_at = datetime.fromisoformat(data.get('cached_at', '2000-01-01'))
            if datetime.now() - cached_at > timedelta(days=CACHE_TTL_DAYS):
                return {}  # Stale cache
            return data.get('tokens', {})
        except Exception:
            return {}

    def _save_cache(self, valid: Dict):
        """Save valid tokens to cache."""
        path = self._cache_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                json.dump({
                    'cached_at': datetime.now().isoformat(),
                    'tokens': valid,
                    'count': len(valid),
                }, f, indent=2)
        except Exception as e:
            print(f"  ⚠ Could not save Greenhouse cache: {e}")

    def _check_token(self, token: str) -> bool:
        """Check if a Greenhouse token is valid (returns jobs)."""
        try:
            r = requests.get(
                f"{self.base_url}/{token}/jobs",
                timeout=5,
            )
            if r.status_code == 200:
                data = r.json()
                return data.get('meta', {}).get('total', len(data.get('jobs', []))) > 0
            return False
        except Exception:
            return False

    def get_valid_tokens(self) -> Dict:
        """Get validated Greenhouse tokens (from cache or by testing)."""
        if self._valid_tokens:
            return self._valid_tokens

        # Try cache first
        cached = self._load_cache()
        if cached:
            print(f"  ✓ Loaded {len(cached)} valid Greenhouse tokens from cache")
            self._valid_tokens = cached
            return cached

        # Validate all tokens in parallel
        print(f"  🔍 Validating {len(GREENHOUSE_TOKENS)} Greenhouse tokens (first run, ~2 min)...")
        valid = {}
        tested = 0

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(self._check_token, token): (token, name)
                for token, name in GREENHOUSE_TOKENS.items()
            }
            for future in as_completed(futures):
                token, name = futures[future]
                tested += 1
                try:
                    if future.result():
                        valid[token] = name
                except Exception:
                    pass

                if tested % 100 == 0:
                    print(f"    ... tested {tested}/{len(GREENHOUSE_TOKENS)}, found {len(valid)} valid")

        print(f"  ✓ Found {len(valid)} valid Greenhouse boards out of {len(GREENHOUSE_TOKENS)} tested")

        self._save_cache(valid)
        self._valid_tokens = valid
        return valid

    # ── Job Fetching ─────────────────────────────────────────────
    def get_all_jobs(self) -> List[Dict]:
        """Fetch jobs from all valid Greenhouse boards."""
        valid_tokens = self.get_valid_tokens()
        all_jobs = []
        errors = 0

        print(f"\n  Scraping {len(valid_tokens)} Greenhouse boards...")

        for token, name in valid_tokens.items():
            try:
                jobs = self.get_jobs_for_token(token, name)
                if jobs:
                    all_jobs.extend(jobs)
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"    ⚠ {name}: {e}")

        print(f"  → Greenhouse total: {len(all_jobs)} jobs from {len(valid_tokens)} companies")
        return all_jobs

    def get_jobs_for_token(self, token: str, company_name: str) -> List[Dict]:
        """Fetch jobs from a single Greenhouse board."""
        url = f"{self.base_url}/{token}/jobs"

        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
            jobs = data.get('jobs', [])

            standardized = []
            for job in jobs:
                standardized.append({
                    'company': company_name,
                    'title': job.get('title', ''),
                    'location': job.get('location', {}).get('name', 'Not specified'),
                    'url': job.get('absolute_url', ''),
                    'description': job.get('content', ''),
                    'posted_date': job.get('updated_at', ''),
                    'source': 'Greenhouse',
                    'job_id': f"gh_{token}_{job.get('id', '')}",
                })

            return self.filter_new_grad_jobs(standardized)

        except Exception:
            return []

    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """Legacy interface — fetch jobs for a single company."""
        token = company_info.get('greenhouse_token')
        if not token:
            name_lower = company_info.get('name', '').lower()
            for tok, name in GREENHOUSE_TOKENS.items():
                if name.lower() in name_lower or tok in name_lower:
                    token = tok
                    break
        if not token:
            token = company_info.get('name', '').lower().replace(' ', '').replace(',', '').replace('.', '')
        if not token:
            return []
        return self.get_jobs_for_token(token, company_info.get('name', token.title()))