"""Greenhouse API client with known company tokens"""

import requests
from typing import List, Dict
from .base import BaseAPIClient


# Known Greenhouse company tokens
GREENHOUSE_TOKENS = {
    'samsara': 'Samsara',
    'stripe': 'Stripe',
    'notion': 'Notion',
    'figma': 'Figma',
    'airtable': 'Airtable',
    'coinbase': 'Coinbase',
    'github': 'GitHub',
    'gitlab': 'GitLab',
    'grammarly': 'Grammarly',
    'intercom': 'Intercom',
    'plaid': 'Plaid',
    'retool': 'Retool',
    'ramp': 'Ramp',
    'webflow': 'Webflow',
    'vanta': 'Vanta',
    'lattice': 'Lattice',
    'flexport': 'Flexport',
    'gusto': 'Gusto',
    'instacart': 'Instacart',
    'doordash': 'DoorDash',
    'faire': 'Faire',
    'benchling': 'Benchling',
    'roblox': 'Roblox',
    'datadog': 'Datadog',
}


class GreenhouseClient(BaseAPIClient):
    """Client for Greenhouse job board API"""
    
    def __init__(self):
        self.base_url = "https://boards-api.greenhouse.io/v1/boards"
    
    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """Fetch jobs from Greenhouse"""
        
        # Try to get token from known list
        token = company_info.get('greenhouse_token')
        
        if not token:
            company_name_lower = company_info.get('name', '').lower()
            for tok, name in GREENHOUSE_TOKENS.items():
                if name.lower() in company_name_lower or tok in company_name_lower:
                    token = tok
                    break
        
        if not token:
            # Try to derive from company name as fallback
            token = company_info.get('name', '').lower().replace(' ', '').replace(',', '').replace('.', '')
        
        if not token:
            return []
        
        url = f"{self.base_url}/{token}/jobs"
        
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 404:
                return []
            
            response.raise_for_status()
            data = response.json()
            
            jobs = data.get('jobs', [])
            standardized_jobs = []
            
            for job in jobs:
                standardized_jobs.append({
                    'company': company_info.get('name', token.title()),
                    'title': job.get('title', ''),
                    'location': job.get('location', {}).get('name', 'Not specified'),
                    'url': job.get('absolute_url', ''),
                    'description': job.get('content', ''),
                    'posted_date': job.get('updated_at', ''),
                    'source': 'Greenhouse',
                    'job_id': f"gh_{token}_{job.get('id', '')}"
                })
            
            return self.filter_new_grad_jobs(standardized_jobs)
            
        except Exception as e:
            print(f"Error fetching Greenhouse jobs for {company_info.get('name', token)}: {e}")
            return []