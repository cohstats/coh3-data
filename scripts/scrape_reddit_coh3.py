#!/usr/bin/env python3
"""
Reddit CoH3 Posts Scraper

Scrapes top monthly posts from r/CompanyOfHeroes with the "CoH3" flair
using Playwright with stealth techniques to bypass Reddit's bot detection.

Usage:
    python scripts/scrape_reddit_coh3.py
"""

import json
import os
import sys
import time
import random
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth


# Configuration
REDDIT_BASE_URL = "https://www.reddit.com"
REDDIT_SEARCH_URL = os.environ.get(
    "REDDIT_URL",
    "https://www.reddit.com/r/CompanyOfHeroes/search.json?q=flair:%22CoH3%22&restrict_sr=1&sort=top&t=month&limit=20"
)
OUTPUT_FILE = "data/reddit_coh3_monthly_top.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def setup_browser(playwright):
    """Initialize browser with stealth configuration."""
    print("🚀 Launching browser with stealth configuration...")

    browser = playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-features=IsolateOrigins,site-per-process',
            '--no-sandbox',
            '--disable-setuid-sandbox',
        ]
    )

    # Create context with realistic settings
    # Note: Stealth is automatically applied via Stealth().use_sync() wrapper in scrape_reddit()
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent=USER_AGENT,
        locale='en-US',
        timezone_id='America/New_York',
        color_scheme='dark',
    )

    return browser, context


def scrape_reddit():
    """Main scraping function."""
    print(f"📡 Starting Reddit CoH3 scraper...")
    print(f"🎯 Target URL: {REDDIT_SEARCH_URL}")

    # Use Stealth wrapper - automatically applies stealth to all pages/contexts
    with Stealth().use_sync(sync_playwright()) as p:
        browser, context = setup_browser(p)
        page = context.new_page()
        
        try:
            # Step 1: Visit Reddit homepage to establish session
            print("🌐 Visiting Reddit homepage to establish session...")
            response1 = page.goto(REDDIT_BASE_URL, wait_until='domcontentloaded', timeout=30000)
            print(f"✅ Homepage response status: {response1.status}")

            # Random delay to mimic human behavior
            delay = random.uniform(2.0, 4.0)
            print(f"⏳ Waiting {delay:.1f}s to mimic human behavior...")
            time.sleep(delay)

            # Step 2: Navigate to JSON API endpoint
            print("📥 Fetching JSON data from search endpoint...")
            response2 = page.goto(REDDIT_SEARCH_URL, wait_until='domcontentloaded', timeout=30000)
            print(f"✅ Search endpoint response status: {response2.status}")

            # Get page content
            content = page.content()

            # Extract JSON from the page (Playwright wraps JSON in HTML)
            # Try to get the text content from the body/pre tag
            print("🔍 Extracting JSON data...")
            try:
                # First, try to get innerText from body which should contain the raw JSON
                json_text = page.evaluate('document.body.innerText')
            except Exception as e:
                print(f"⚠️  Could not extract via innerText, trying content parsing: {e}")
                json_text = content

            # Check if we got actual JSON or an error page
            # Valid Reddit JSON should start with '{' and contain "kind" and "data"
            json_text = json_text.strip()
            if not json_text.startswith('{'):
                print("❌ ERROR: Response doesn't start with JSON - likely bot detection or error!")
                print("💡 This might be Cloudflare or Reddit's bot protection.")
                # Save error page for debugging
                error_file = f"data/reddit_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                Path("data").mkdir(exist_ok=True)
                with open(error_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"📄 Error page saved to: {error_file}")
                print(f"📄 First 500 chars: {json_text[:500]}")
                sys.exit(1)

            # Validate JSON response
            print("🔍 Validating JSON response...")
            json_data = json.loads(json_text)

            # Count posts if available
            post_count = 0
            if 'data' in json_data and 'children' in json_data['data']:
                post_count = len(json_data['data']['children'])

            print(f"✅ Successfully retrieved JSON with {post_count} posts")

            # Save raw JSON to file
            Path("data").mkdir(exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)

            print(f"💾 Raw JSON data saved to: {OUTPUT_FILE}")
            return True
            
        except PlaywrightTimeout as e:
            print(f"❌ Timeout error: {e}")
            return False
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    success = scrape_reddit()
    sys.exit(0 if success else 1)
