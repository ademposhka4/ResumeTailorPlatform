"""
Experience Service Layer
Handles validation and business logic for experience management.
"""
import uuid
from datetime import datetime
import logging
import os
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from .models import ExperienceGraph

logger = logging.getLogger(__name__)


class ExperienceService:
    """Service for managing user experiences with validation."""
    
    VALID_TYPES = ['work', 'education', 'project', 'volunteer']
    
    @staticmethod
    def validate_experience(data: Dict) -> Dict:
        """
        Validate experience data structure and types.
        
        Args:
            data: Dictionary with experience fields
            
        Returns:
            Cleaned data dictionary
            
        Raises:
            ValidationError: If validation fails
        """
        errors = []
        
        # Required fields
        required = ['type', 'title', 'organization']
        for field in required:
            if not data.get(field):
                errors.append(f"{field} is required")
        
        # Type validation
        if data.get('type') and data['type'] not in ExperienceService.VALID_TYPES:
            errors.append(f"type must be one of: {', '.join(ExperienceService.VALID_TYPES)}")
        
        # Date validation
        start_date = data.get('start_date', '')
        end_date = data.get('end_date', '')
        current = data.get('current', False)
        
        if start_date:
            try:
                datetime.strptime(start_date, '%Y-%m')
            except ValueError:
                errors.append("start_date must be in YYYY-MM format")
        
        if end_date and not current:
            try:
                datetime.strptime(end_date, '%Y-%m')
            except ValueError:
                errors.append("end_date must be in YYYY-MM format")
        
        if current and end_date:
            errors.append("end_date should be empty when current is true")
        
        # Skills must be a list
        skills = data.get('skills', [])
        if not isinstance(skills, list):
            errors.append("skills must be a list")
        
        # Achievements must be a list
        achievements = data.get('achievements', [])
        if not isinstance(achievements, list):
            errors.append("achievements must be a list")
        
        if errors:
            raise ValidationError(errors)
        
        # Return cleaned data
        return {
            'id': data.get('id', str(uuid.uuid4())),
            'type': data['type'],
            'title': data['title'],
            'organization': data['organization'],
            'location': data.get('location', ''),
            'start_date': start_date,
            'end_date': end_date if not current else '',
            'current': current,
            'description': data.get('description', ''),
            'skills': skills,
            'achievements': achievements
        }
    
    @staticmethod
    def get_experience_graph(user) -> ExperienceGraph:
        """Get or create experience graph for user."""
        graph, created = ExperienceGraph.objects.get_or_create(
            user=user,
            defaults={'graph_json': {'experiences': []}}
        )
        # Ensure experiences key exists
        if 'experiences' not in graph.graph_json:
            graph.graph_json['experiences'] = []
            graph.save()
        return graph
    
    @staticmethod
    def get_experiences(user) -> List[Dict]:
        """
        Get all experiences for a user, sorted by date.
        
        Args:
            user: Django user instance
            
        Returns:
            List of experience dictionaries
        """
        graph = ExperienceService.get_experience_graph(user)
        experiences = graph.graph_json.get('experiences', [])
        
        # Sort by start_date (most recent first)
        def sort_key(exp):
            start = exp.get('start_date', '')
            # Current jobs go first, then by start date descending
            if exp.get('current'):
                return ('9999-99', exp.get('title', ''))
            return (start if start else '0000-00', exp.get('title', ''))
        
        return sorted(experiences, key=sort_key, reverse=True)
    
    @staticmethod
    def get_experience_by_id(user, experience_id: str) -> Optional[Dict]:
        """
        Get a specific experience by ID.
        
        Args:
            user: Django user instance
            experience_id: UUID string of experience
            
        Returns:
            Experience dictionary or None
        """
        experiences = ExperienceService.get_experiences(user)
        for exp in experiences:
            if exp.get('id') == experience_id:
                return exp
        return None
    
    @staticmethod
    def add_experience(user, data: Dict) -> Dict:
        """
        Add a new experience for a user.
        
        Args:
            user: Django user instance
            data: Experience data dictionary
            
        Returns:
            Created experience with assigned ID
            
        Raises:
            ValidationError: If validation fails
        """
        # Validate and clean data
        clean_data = ExperienceService.validate_experience(data)
        ExperienceService._populate_coordinates(clean_data)
        
        # Get graph and add experience
        graph = ExperienceService.get_experience_graph(user)
        graph.graph_json['experiences'].append(clean_data)
        graph.save()
        
        return clean_data
    
    @staticmethod
    def update_experience(user, experience_id: str, data: Dict) -> Dict:
        """
        Update an existing experience.
        
        Args:
            user: Django user instance
            experience_id: UUID string of experience
            data: Updated experience data
            
        Returns:
            Updated experience dictionary
            
        Raises:
            ValidationError: If validation fails or experience not found
        """
        existing = ExperienceService.get_experience_by_id(user, experience_id)
        existing_location = ''
        existing_coordinates = None
        if existing:
            existing_location = existing.get('location', '')
            existing_coordinates = existing.get('coordinates')
        
        # Validate and clean data (preserve existing ID)
        data['id'] = experience_id
        clean_data = ExperienceService.validate_experience(data)
        
        if existing_coordinates and existing_location.strip().lower() == clean_data.get('location', '').strip().lower():
            clean_data['coordinates'] = existing_coordinates
        else:
            ExperienceService._populate_coordinates(clean_data)
        
        # Get graph and find experience
        graph = ExperienceService.get_experience_graph(user)
        experiences = graph.graph_json['experiences']
        
        for i, exp in enumerate(experiences):
            if exp.get('id') == experience_id:
                experiences[i] = clean_data
                graph.save()
                return clean_data
        
        raise ValidationError(f"Experience with id {experience_id} not found")
    
    @staticmethod
    def delete_experience(user, experience_id: str) -> bool:
        """
        Delete an experience.
        
        Args:
            user: Django user instance
            experience_id: UUID string of experience
            
        Returns:
            True if deleted, False if not found
        """
        graph = ExperienceService.get_experience_graph(user)
        experiences = graph.graph_json['experiences']
        
        original_length = len(experiences)
        graph.graph_json['experiences'] = [
            exp for exp in experiences if exp.get('id') != experience_id
        ]
        
        if len(graph.graph_json['experiences']) < original_length:
            graph.save()
            return True
        return False

    @staticmethod
    def _populate_coordinates(experience: Dict) -> Dict:
        """
        Attach geocoded coordinates to an experience if possible.
        """
        location = (experience.get('location') or '').strip()
        if not location:
            experience.pop('coordinates', None)
            return experience

        token = (
            os.environ.get('MAPBOX_TOKEN')
            or getattr(settings, 'MAPBOX_TOKEN', '')
        )
        if not token:
            return experience

        try:
            query = quote_plus(location)
            response = requests.get(
                f"https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json",
                params={
                    'access_token': token,
                    'limit': 1,
                    'autocomplete': 'false'
                },
                timeout=5,
            )
            response.raise_for_status()
            payload = response.json()
            features = payload.get('features') or []
            if not features:
                return experience

            first = features[0]
            coords = first.get('geometry', {}).get('coordinates')
            if not coords or len(coords) < 2:
                return experience

            experience['coordinates'] = {
                'longitude': float(coords[0]),
                'latitude': float(coords[1]),
                'source': 'mapbox',
                'relevance': first.get('relevance'),
                'matched_text': first.get('place_name'),
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to geocode location '%s': %s", location, exc)
            experience.pop('coordinates', None)

        return experience
