#!/usr/bin/env python
"""
Integration test for the full tailoring workflow with web search support.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myapply.settings')
django.setup()

from tailoring.services import AgentKitTailoringService
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_full_workflow_with_url():
    """Test the complete workflow with URL (even if web search fails, it should still work)."""
    print(f"\n{'='*80}")
    print("Testing Full Tailoring Workflow with URL")
    print('='*80)
    
    # Sample experience graph (minimal)
    experience_graph = {
        "experiences": [
            {
                "id": "exp-1",
                "title": "Senior Software Engineer",
                "company": "Tech Corp",
                "start": "2021-01",
                "end": "Present",
                "current": True,
                "description": "Led development of cloud-native applications",
                "achievements": [
                    "Built microservices architecture serving 1M+ users",
                    "Reduced API latency by 60% through optimization",
                    "Mentored team of 5 junior engineers",
                ],
                "skills": ["Python", "AWS", "Docker", "Kubernetes", "PostgreSQL"],
            }
        ],
        "projects": [
            {
                "id": "proj-1",
                "title": "Open Source Contributor",
                "organization": "Personal",
                "start": "2020-06",
                "description": "Contributed to various OSS projects",
                "achievements": [
                    "Submitted 15+ PRs to major Python frameworks",
                    "Fixed critical security vulnerabilities",
                ],
                "skills": ["Python", "Git", "Open Source"],
            }
        ],
    }
    
    # Test with URL (will attempt web search but should handle failure gracefully)
    test_url = "https://delta.avature.net/en_US/careers/JobDetail/Specialist-Metrics-Reporting/28553?jobId=28553"
    
    try:
        service = AgentKitTailoringService()
        
        print("\n1. Running workflow with job URL...")
        print(f"   URL: {test_url}")
        
        result = service.run_workflow(
            job_description="",  # Empty - will try to fetch from URL
            experience_graph=experience_graph,
            source_url=test_url,
            parameters={
                "bullets_per_section": 3,
                "sections": ["Professional Experience", "Projects"],
                "include_summary": True,
            }
        )
        
        print("\n2. Workflow completed successfully!")
        print(f"\n   Results:")
        print(f"   - Title: {result.get('title', 'N/A')}")
        print(f"   - Summary length: {len(result.get('summary', ''))} chars")
        print(f"   - Sections: {len(result.get('sections', []))}")
        print(f"   - Total bullets: {len(result.get('bullets', []))}")
        print(f"   - ATS Score: {result.get('ats_score', {}).get('overall_score', 0)}%")
        print(f"   - Token usage: {result.get('token_usage', {})}")
        
        # Check requirements extraction
        requirements = result.get('debug', {}).get('requirements', {})
        print(f"\n   Requirements extracted:")
        print(f"   - Keywords: {len(requirements.get('keywords', []))}")
        print(f"   - Required skills: {len(requirements.get('required_skills', []))}")
        print(f"   - Preferred skills: {len(requirements.get('preferred_skills', []))}")
        
        if requirements.get('keywords'):
            print(f"   - Sample keywords: {requirements['keywords'][:10]}")
        
        # Verify bullet distribution
        sections = result.get('sections', [])
        print(f"\n   Bullet distribution:")
        for section in sections:
            print(f"   - {section.get('name')}: {len(section.get('bullets', []))} bullets")
        
        # Check if web search provided requirements
        if requirements.get('keywords') and len(requirements['keywords']) > 0:
            print("\n✓ Web search successfully extracted job requirements!")
            return True
        else:
            print("\n⚠️  Web search did not extract requirements (likely blocked)")
            print("   However, workflow completed successfully with empty requirements.")
            return True  # Still consider it a pass since the workflow didn't crash
            
    except Exception as e:
        print(f"\n✗ Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_workflow_with_description():
    """Test workflow with provided job description (no web search needed)."""
    print(f"\n{'='*80}")
    print("Testing Full Tailoring Workflow with Job Description")
    print('='*80)
    
    job_description = """
    Senior Software Engineer
    
    We are seeking an experienced Senior Software Engineer to join our team.
    
    Required Skills:
    - 5+ years Python development
    - AWS, Docker, Kubernetes
    - PostgreSQL, Redis
    - Microservices architecture
    - REST APIs
    
    Responsibilities:
    - Design and implement scalable backend systems
    - Lead technical architecture decisions
    - Mentor junior engineers
    - Optimize application performance
    
    Preferred Skills:
    - Go or Rust experience
    - Machine learning familiarity
    - Open source contributions
    """
    
    experience_graph = {
        "experiences": [
            {
                "id": "exp-1",
                "title": "Senior Software Engineer",
                "company": "Tech Corp",
                "start": "2021-01",
                "end": "Present",
                "current": True,
                "description": "Led development of cloud-native applications",
                "achievements": [
                    "Built microservices architecture serving 1M+ users",
                    "Reduced API latency by 60% through optimization",
                    "Mentored team of 5 junior engineers",
                ],
                "skills": ["Python", "AWS", "Docker", "Kubernetes", "PostgreSQL"],
            }
        ],
    }
    
    try:
        service = AgentKitTailoringService()
        
        print("\n1. Running workflow with job description...")
        
        result = service.run_workflow(
            job_description=job_description,
            experience_graph=experience_graph,
            parameters={
                "bullets_per_section": 2,
                "sections": ["Professional Experience"],
                "include_summary": True,
            }
        )
        
        print("\n2. Workflow completed successfully!")
        print(f"\n   Results:")
        print(f"   - Title: {result.get('title', 'N/A')}")
        print(f"   - ATS Score: {result.get('ats_score', {}).get('overall_score', 0)}%")
        
        requirements = result.get('debug', {}).get('requirements', {})
        print(f"\n   Requirements extracted:")
        print(f"   - Keywords: {len(requirements.get('keywords', []))} items")
        print(f"   - Required skills: {len(requirements.get('required_skills', []))} items")
        
        if len(requirements.get('keywords', [])) > 5:
            print("\n✓ Successfully extracted requirements from job description!")
            return True
        else:
            print("\n✗ Failed to extract requirements")
            return False
            
    except Exception as e:
        print(f"\n✗ Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    results = []
    
    # Test 1: With job description (should always work)
    print("\n" + "="*80)
    print("TEST 1: Workflow with Job Description (No Web Search)")
    print("="*80)
    results.append(("With Description", test_workflow_with_description()))
    
    # Test 2: With URL (may be blocked, but should handle gracefully)
    print("\n" + "="*80)
    print("TEST 2: Workflow with URL (Web Search - may be blocked)")
    print("="*80)
    results.append(("With URL", test_full_workflow_with_url()))
    
    # Summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print('='*80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All integration tests passed!")
    else:
        print("\n⚠️  Some tests failed. Check the logs above for details.")
