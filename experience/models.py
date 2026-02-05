"""
Experience app models

ExperienceGraph model for storing user's professional experience as JSON.

Expected JSON schema:
{
  "experiences": [
    {
      "title": "Operations Analyst Co-op",
      "company": "Delta Air Lines",
      "start": "2024-01",
      "end": "2024-08",
      "skills": ["python", "sql", "smartsheet", "etl"],
      "achievements": [
        "Automated pilot work reporting",
        "Improved delay reporting accuracy"
      ]
    }
  ]
}
"""
from django.conf import settings
from django.db import models


class ExperienceGraph(models.Model):
    """
    Store user's experience graph as structured JSON.
    
    The graph_json field should contain a dictionary with an "experiences" key
    containing a list of experience objects with title, company, dates, skills, 
    and achievements.
    """
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='experience_graph',
    )
    graph_json = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Experience graph for {self.user.username}"
    
    class Meta:
        verbose_name = 'Experience Graph'
        verbose_name_plural = 'Experience Graphs'
