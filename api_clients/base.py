"""Base class for career site API clients"""

from typing import List, Dict, Optional
from abc import ABC, abstractmethod

class BaseAPIClient(ABC):
    """Base class for all ATS API clients"""
    
    @abstractmethod
    def get_jobs(self, company_info: Dict) -> List[Dict]:
        """
        Fetch jobs from the career site
        
        Args:
            company_info: Dict with company details (name, url, etc.)
            
        Returns:
            List of job dictionaries with standardized format:
            {
                'company': str,
                'title': str,
                'location': str,
                'url': str,
                'description': str,  # Full job description
                'posted_date': str,
                'source': str  # ATS type
            }
        """
        pass
    
    def filter_new_grad_jobs(self, jobs: List[Dict]) -> List[Dict]:
        """Filter for new grad related positions"""
        keywords = [
        'new grad', 'early career', 'entry', 'junior', 'associate',
        '0-2 years', '0-3 years', 'recent graduate', 'entry-level',
        'university grad', 'campus'
        ]
        exclude_keywords = ['senior', 'staff', 'principal', 'lead', 'manager', '3+', '5+']
        
        filtered = []
        for job in jobs:
            title_lower = job.get('title', '').lower()
            desc_lower = job.get('description', '').lower()
            
            # Must have new grad keywords
            has_new_grad = any(kw in title_lower or kw in desc_lower for kw in keywords)
            
            # Must NOT have senior keywords
            has_senior = any(kw in title_lower for kw in exclude_keywords)
            
            if has_new_grad and not has_senior:
                filtered.append(job)
        
        return filtered
