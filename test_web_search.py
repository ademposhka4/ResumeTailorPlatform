#!/usr/bin/env python
"""
Test script to validate OpenAI web search functionality for job posting extraction.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myapply.settings')
django.setup()

from tailoring.services import AgentKitTailoringService
import logging

# Configure logging to see details
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def test_web_search(url: str):
    """Test fetching job description from URL."""
    print(f"\n{'='*80}")
    print(f"Testing web search for: {url}")
    print('='*80)
    
    try:
        service = AgentKitTailoringService()
        
        print("\n1. Fetching job description from URL...")
        description = service._fetch_job_description_from_url(url)
        
        if description:
            print(f"✓ Successfully fetched {len(description)} characters")
            print(f"\nFirst 500 chars of description:")
            print('-' * 80)
            print(description[:500])
            print('-' * 80)
            
            # Test requirement extraction
            print("\n2. Extracting requirements...")
            requirements = service._extract_job_requirements(description)
            
            print(f"\nExtracted requirements:")
            print(f"  - Skills: {len(requirements.get('skills', []))} items")
            if requirements.get('skills'):
                print(f"    Sample: {requirements['skills'][:5]}")
            
            print(f"  - Required Skills: {len(requirements.get('required_skills', []))} items")
            if requirements.get('required_skills'):
                print(f"    Sample: {requirements['required_skills'][:5]}")
            
            print(f"  - Keywords: {len(requirements.get('keywords', []))} items")
            if requirements.get('keywords'):
                print(f"    Sample: {requirements['keywords'][:10]}")
            
            print(f"  - Responsibilities: {len(requirements.get('responsibilities', []))} items")
            print(f"  - Qualifications: {len(requirements.get('qualifications', []))} items")
            
            print(f"\n✓ Web search test PASSED")
            return True
        else:
            print(f"✗ Failed to fetch description - returned empty")
            return False
            
    except Exception as e:
        print(f"\n✗ Test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Test URLs - using publicly accessible pages
    # Note: Most job sites (LinkedIn, Indeed, Avature) block automated access
    test_urls = [
        # Try a tech company careers page
        "https://www.greenhouse.io/job-board/",
        # NASA careers (often more open)
        "https://www.nasa.gov/careers/",
        # Test with the Delta URL anyway to confirm proper error handling
        "https://delta.avature.net/en_US/careers/JobDetail/Specialist-Metrics-Reporting/28553?jobId=28553",
    ]
    
    results = []
    for url in test_urls:
        success = test_web_search(url)
        results.append((url, success))
    
    # Summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print('='*80)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for url, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {url}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Web search is working correctly.")
    else:
        print("\n⚠️  Some tests failed. Check the logs above for details.")
