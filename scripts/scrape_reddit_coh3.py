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


def extract_post_data(post_data):
    """Extract relevant fields from a Reddit post."""
    try:
        return {
            'title': post_data.get('title', ''),
            'author': post_data.get('author', '[deleted]'),
            'score': post_data.get('score', 0),
            'upvote_ratio': post_data.get('upvote_ratio', 0),
            'num_comments': post_data.get('num_comments', 0),
            'created_utc': post_data.get('created_utc', 0),
            'created_date': datetime.fromtimestamp(post_data.get('created_utc', 0)).isoformat(),
            'permalink': f"https://www.reddit.com{post_data.get('permalink', '')}",
            'url': post_data.get('url', ''),
            'selftext': post_data.get('selftext', ''),
            'is_self': post_data.get('is_self', False),
            'link_flair_text': post_data.get('link_flair_text', ''),
            'id': post_data.get('id', ''),
        }
    except Exception as e:
        print(f"⚠️  Error extracting post data: {e}")
        return None


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
            page.goto(REDDIT_BASE_URL, wait_until='domcontentloaded', timeout=30000)
            
            # Random delay to mimic human behavior
            delay = random.uniform(2.0, 4.0)
            print(f"⏳ Waiting {delay:.1f}s to mimic human behavior...")
            time.sleep(delay)
            
            # Step 2: Navigate to JSON API endpoint
            print("📥 Fetching JSON data from search endpoint...")
            page.goto(REDDIT_SEARCH_URL, wait_until='domcontentloaded', timeout=30000)
            
            # Get page content
            content = page.content()
            
            # Check if we got JSON or HTML (bot detection)
            if '<html' in content.lower():
                print("❌ ERROR: Received HTML instead of JSON - likely bot detection!")
                print("💡 This might be Cloudflare or Reddit's bot protection.")
                # Save error page for debugging
                error_file = f"data/reddit_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                Path("data").mkdir(exist_ok=True)
                with open(error_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"📄 Error page saved to: {error_file}")
                sys.exit(1)
            
            # Parse JSON response
            print("🔍 Parsing JSON response...")
            json_data = json.loads(page.evaluate('document.body.innerText'))
            
            # Extract posts
            posts = []
            if 'data' in json_data and 'children' in json_data['data']:
                for child in json_data['data']['children']:
                    if child.get('kind') == 't3':  # t3 = post/link
                        post_data = extract_post_data(child['data'])
                        if post_data:
                            posts.append(post_data)
            
            print(f"✅ Successfully extracted {len(posts)} posts")
            
            # Prepare output
            output = {
                'metadata': {
                    'scrape_timestamp': datetime.now().isoformat(),
                    'scrape_timestamp_utc': datetime.utcnow().isoformat() + 'Z',
                    'query_url': REDDIT_SEARCH_URL,
                    'total_posts': len(posts),
                },
                'posts': posts
            }
            
            # Save to file
            Path("data").mkdir(exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Data saved to: {OUTPUT_FILE}")
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
