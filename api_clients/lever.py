"""Lever API client"""

import requests
from typing import List, Dict
from .base import BaseAPIClient


class LeverClient(BaseAPIClient):
    """Client for Lever job board API"""
    
    def __init__(self):
        self.base_url = "https://api.lever.co/v0/postings"
    
    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """Fetch jobs from Lever"""
        
        company_name = company_info.get('lever_name') or \
                      company_info.get('name', '').lower().replace(' ', '').replace(',', '')
        
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
