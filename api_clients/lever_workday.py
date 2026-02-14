"""Lever and Workday API clients"""

import requests
from typing import List, Dict
from .base import BaseAPIClient

class LeverClient(BaseAPIClient):
    """Client for Lever job board API"""
    
    def __init__(self):
        self.base_url = "https://api.lever.co/v0/postings"
    
    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """Fetch jobs from Lever"""
        
        company_name = company_info.get('lever_name') or company_info.get('name', '').lower().replace(' ', '')
        
        url = f"{self.base_url}/{company_name}?mode=json"
        
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 404:
                return []
            
            response.raise_for_status()
            jobs = response.json()
            
            standardized_jobs = []
            
            for job in jobs:
                standardized_jobs.append({
                    'company': company_info.get('name', company_name.title()),
                    'title': job.get('text', ''),
                    'location': job.get('categories', {}).get('location', 'Not specified'),
                    'url': job.get('hostedUrl', ''),
                    'description': job.get('description', ''),
                    'posted_date': job.get('createdAt', ''),
                    'source': 'Lever',
                    'job_id': f"lv_{company_name}_{job.get('id', '')}"
                })
            
            return self.filter_new_grad_jobs(standardized_jobs)
            
        except Exception as e:
            print(f"Error fetching Lever jobs for {company_info.get('name')}: {e}")
            return []


class WorkdayClient(BaseAPIClient):
    """
    Client for Workday careers sites
    
    NOTE: Workday requires reverse engineering per company!
    This is a TEMPLATE. You'll need to find the actual API endpoint.
    
    How to find it:
    1. Open company's Workday careers page
    2. DevTools → Network → XHR
    3. Search for jobs
    4. Look for POST to /wday/cxs/ endpoint
    5. Copy the exact URL and payload structure
    """
    
    def __init__(self):
        self.endpoints = {}  # Will store company-specific endpoints
    
    def add_endpoint(self, company_name: str, endpoint_url: str, payload_template: Dict):
        """Register a Workday endpoint after reverse engineering"""
        self.endpoints[company_name.lower()] = {
            'url': endpoint_url,
            'payload': payload_template
        }
    
    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """
        Fetch jobs from Workday
        
        company_info should have 'workday_endpoint' and 'workday_payload'
        OR company must be registered via add_endpoint()
        """
        
        company_name = company_info.get('name', '').lower()
        
        # Check if we have a registered endpoint
        if company_name in self.endpoints:
            config = self.endpoints[company_name]
            url = config['url']
            payload = config['payload'].copy()
        else:
            # Try to use provided endpoint
            url = company_info.get('workday_endpoint')
            payload = company_info.get('workday_payload', {
                "appliedFacets": {},
                "limit": 20,
                "offset": 0,
                "searchText": ""
            })
        
        if not url:
            print(f"No Workday endpoint configured for {company_info.get('name')}")
            return []
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # NOTE: Response structure varies by company!
            # You'll need to adapt this based on what the API returns
            jobs = data.get('jobPostings', []) or data.get('jobs', [])
            
            standardized_jobs = []
            
            for job in jobs:
                standardized_jobs.append({
                    'company': company_info.get('name', company_name.title()),
                    'title': job.get('title', '') or job.get('jobTitle', ''),
                    'location': job.get('location', '') or job.get('locationString', ''),
                    'url': job.get('externalUrl', '') or job.get('url', ''),
                    'description': job.get('description', ''),
                    'posted_date': job.get('postedOn', '') or job.get('postingDate', ''),
                    'source': 'Workday',
                    'job_id': f"wd_{company_name}_{job.get('bulletFields', [''])[0] if 'bulletFields' in job else job.get('id', '')}"
                })
            
            return self.filter_new_grad_jobs(standardized_jobs)
            
        except Exception as e:
            print(f"Error fetching Workday jobs for {company_info.get('name')}: {e}")
            return []


# Example of how to register a Workday endpoint after reverse engineering:
"""
workday_client = WorkdayClient()

# After reverse engineering Google's Workday:
workday_client.add_endpoint(
    company_name="Google",
    endpoint_url="https://www.google.com/about/careers/applications/api/v2/jobs/search",
    payload_template={
        "query": "",
        "page": 1,
        "limit": 100
    }
)
"""