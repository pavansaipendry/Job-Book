"""Email notification system"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from datetime import datetime

class EmailNotifier:
    """Sends email notifications for new jobs"""
    
    def __init__(self, config: Dict):
        self.from_email = config.get('from')
        self.to_email = config.get('to')
        self.smtp_server = config.get('smtp_server')
        self.smtp_port = config.get('smtp_port')
        self.password = config.get('password')
    
    def send_instant_alert(self, job: Dict):
        """Send instant alert for high-scoring job"""
        
        subject = f"🚨 NEW JOB MATCH (Score: {int(job.get('score', 0))}) - {job.get('company')}"
        
        body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <h2 style="color: #2ecc71;">New Job Match!</h2>
    
    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
        <h3 style="margin-top: 0; color: #333;">{job.get('title')}</h3>
        <p><strong>Company:</strong> {job.get('company')}</p>
        <p><strong>Location:</strong> {job.get('location')}</p>
        <p><strong>Score:</strong> {int(job.get('score', 0))}/100</p>
        <p><strong>Posted:</strong> {job.get('posted_date', 'Recently')}</p>
    </div>
    
    <div style="margin: 20px 0;">
        <h4>Why this is a good match:</h4>
        <pre style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; white-space: pre-wrap;">
{job.get('score_explanation', 'Good skill match with your profile')}
        </pre>
    </div>
    
    <div style="margin: 30px 0;">
        <a href="{job.get('url')}" 
           style="background-color: #3498db; color: white; padding: 15px 30px; 
                  text-decoration: none; border-radius: 5px; display: inline-block; 
                  font-weight: bold;">
            APPLY NOW →
        </a>
    </div>
    
    <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
    
    <p style="color: #7f8c8d; font-size: 12px;">
        Found by your automated job scraper • {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
    </p>
</body>
</html>
        """
        
        self._send_email(subject, body)
    
    def send_digest(self, jobs: List[Dict], total_new: int = None):
        """Send single digest email with top jobs"""
        
        if not jobs:
            return
        
        total = total_new or len(jobs)
        subject = f"⚡ Top {len(jobs)} Job Matches — {total} new jobs found"
        
        jobs_html = ""
        for i, job in enumerate(jobs[:5], 1):
            score = int(job.get('score', 0))
            color = '#22c55e' if score >= 60 else '#eab308' if score >= 40 else '#f97316'
            jobs_html += f"""
            <div style="background-color: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 8px; border-left: 4px solid {color};">
                <h4 style="margin: 0 0 8px 0;">{i}. {job.get('title')}</h4>
                <p style="margin: 4px 0;"><strong>{job.get('company')}</strong> — {job.get('location', 'N/A')}</p>
                <p style="margin: 4px 0;">Score: <strong style="color: {color};">{score}/100</strong> &nbsp;·&nbsp; {job.get('source', '')}</p>
                <a href="{job.get('url')}" style="color: #3498db; text-decoration: none; font-weight: bold;">Apply →</a>
            </div>
            """
        
        remaining = total - len(jobs)
        footer = f"<p style='text-align:center; color:#7f8c8d;'>+ {remaining} more jobs in your dashboard</p>" if remaining > 0 else ""
        
        body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; max-width: 600px; margin: 0 auto;">
    <h2 style="color: #38bdf8;">⚡ Your Top Job Matches</h2>
    <p>Found <strong>{total} new jobs</strong>. Here are the top {len(jobs)}:</p>
    {jobs_html}
    {footer}
    <hr style="margin: 30px 0; border: none; border-top: 1px solid #ddd;">
    <p style="color: #7f8c8d; font-size: 12px;">
        Job Scraper · {datetime.now().strftime('%B %d, %Y at %I:%M %p')} · <a href="http://localhost:5000">Open Dashboard</a>
    </p>
</body>
</html>
        """
        
        self._send_email(subject, body)
    
    def _send_email(self, subject: str, body_html: str):
        """Internal method to send email"""
        
        # Skip if password not configured
        if not self.password or self.password in ('a', 'your_app_password', 'placeholder', ''):
            print(f"⏭️  Email skipped (no app password configured): {subject[:60]}")
            return
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = self.to_email
            
            # Add HTML body
            html_part = MIMEText(body_html, 'html')
            msg.attach(html_part)
            
            # Send via Gmail SMTP
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.from_email, self.password)
                server.send_message(msg)
            
            print(f"✅ Email sent: {subject}")
            
        except Exception as e:
            print(f"❌ Error sending email: {e}")
    
    def send_test_email(self):
        """Send test email to verify configuration"""
        
        subject = "🧪 Job Scraper Test Email"
        body = """
<html>
<body style="font-family: Arial, sans-serif;">
    <h2>Test Email Successful!</h2>
    <p>Your job scraper email notifications are working correctly.</p>
    <p>You'll receive alerts here when new jobs match your criteria.</p>
</body>
</html>
        """
        
        self._send_email(subject, body)