"""
Social Media Executor v2
Automated social media posting using Playwright async API.
Supports: LinkedIn, Facebook, Instagram, Twitter (X)
"""

import asyncio
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml
from playwright.async_api import async_playwright, BrowserContext, Page


# Configuration
SESSION_DIR = "./session"
LOGS_DIR = "./Logs"

# Platform URLs
PLATFORM_URLS = {
    "linkedin": "https://www.linkedin.com/feed/",
    "facebook": "https://www.facebook.com/",
    "instagram": "https://www.instagram.com/",
    "twitter": "https://twitter.com/home",
}


def ensure_directories():
    """Ensure session and logs directories exist."""
    Path(SESSION_DIR).mkdir(parents=True, exist_ok=True)
    Path(LOGS_DIR).mkdir(parents=True, exist_ok=True)


def parse_markdown_file(filepath: str) -> dict:
    """Parse markdown file with YAML frontmatter."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract YAML frontmatter between ---
    pattern = r"^---\s*\n(.*?)\n---"
    match = re.search(pattern, content, re.DOTALL)

    if not match:
        raise ValueError("No YAML frontmatter found in markdown file")

    yaml_content = match.group(1)
    metadata = yaml.safe_load(yaml_content)

    return metadata


async def take_error_screenshot(page: Page, platform: str, error_msg: str) -> str:
    """Take screenshot on error and save to Logs directory."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{platform}_error_{timestamp}.png"
    filepath = os.path.join(LOGS_DIR, filename)

    await page.screenshot(path=filepath, full_page=True)

    # Also save error details
    log_file = os.path.join(LOGS_DIR, f"{platform}_error_{timestamp}.txt")
    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"Platform: {platform}\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"Error: {error_msg}\n")
        f.write(f"Screenshot: {filename}\n")

    return filepath


async def post_linkedin(page: Page, content: str) -> dict:
    """Post content to LinkedIn."""
    platform = "linkedin"

    try:
        # Navigate to LinkedIn feed
        await page.goto(PLATFORM_URLS["linkedin"], wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Click "Start a post" button
        start_post_selectors = [
            'button:has-text("Start a post")',
            '[data-test-id="share-box-feed-entry__trigger"]',
            '.share-box-feed-entry__trigger',
            'button[aria-label="Start a post"]',
        ]

        clicked = False
        for selector in start_post_selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=3000):
                    await button.click()
                    clicked = True
                    break
            except:
                continue

        if not clicked:
            raise Exception("Could not find 'Start a post' button")

        await page.wait_for_timeout(1500)

        # Find the post editor and type content
        editor_selectors = [
            '[data-test-id="share-to-feed-modal__text-editor"]',
            '.ql-editor[contenteditable="true"]',
            '[role="textbox"][aria-label*="share"]',
            '[contenteditable="true"][aria-placeholder*="share"]',
            '.editor-content[contenteditable="true"]',
            '[data-placeholder*="share"]',
        ]

        typed = False
        for selector in editor_selectors:
            try:
                editor = page.locator(selector).first
                if await editor.is_visible(timeout=3000):
                    await editor.click()
                    await page.keyboard.type(content, delay=30)
                    typed = True
                    break
            except:
                continue

        if not typed:
            raise Exception("Could not find post editor")

        await page.wait_for_timeout(1000)

        # Click Post button
        post_button_selectors = [
            'button:has-text("Post")',
            '[data-test-id="share-actions__primary-action"]',
            'button.share-actions__primary-action',
        ]

        posted = False
        for selector in post_button_selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=3000):
                    await button.click()
                    posted = True
                    break
            except:
                continue

        if not posted:
            raise Exception("Could not find Post button")

        # Wait for success indicator
        await page.wait_for_timeout(3000)

        # Check for success (modal closes or success message)
        try:
            success_indicators = [
                'text="Post successful"',
                'text="Your post was shared"',
            ]
            for indicator in success_indicators:
                if await page.locator(indicator).is_visible(timeout=2000):
                    break
        except:
            pass  # Continue even if success indicator not found

        return {"success": True, "message": "LinkedIn post published successfully", "platform": platform}

    except Exception as e:
        error_msg = str(e)
        screenshot_path = await take_error_screenshot(page, platform, error_msg)
        return {
            "success": False,
            "message": f"LinkedIn posting failed: {error_msg}",
            "platform": platform,
            "screenshot": screenshot_path,
        }


async def post_facebook(page: Page, content: str) -> dict:
    """Post content to Facebook."""
    platform = "facebook"

    try:
        # Navigate to Facebook
        await page.goto(PLATFORM_URLS["facebook"], wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Click "What's on your mind?" to open post composer
        composer_selectors = [
            '[aria-label="Create a post"]',
            '[data-testid="status-attachment-mentions-input"]',
            'span:has-text("What\'s on your mind")',
            '[role="button"]:has-text("What\'s on your mind")',
            'div[role="textbox"][aria-placeholder*="mind"]',
        ]

        clicked = False
        for selector in composer_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=3000):
                    await element.click()
                    clicked = True
                    break
            except:
                continue

        if not clicked:
            raise Exception("Could not find post composer")

        await page.wait_for_timeout(1500)

        # Type in the post editor
        editor_selectors = [
            '[contenteditable="true"][role="textbox"]',
            '[data-testid="status-attachment-mentions-input"]',
            'div[contenteditable="true"][aria-describedby]',
            'form [contenteditable="true"]',
        ]

        typed = False
        for selector in editor_selectors:
            try:
                editor = page.locator(selector).first
                if await editor.is_visible(timeout=3000):
                    await editor.click()
                    await page.keyboard.type(content, delay=30)
                    typed = True
                    break
            except:
                continue

        if not typed:
            raise Exception("Could not find post editor")

        await page.wait_for_timeout(1000)

        # Click Post button
        post_button_selectors = [
            '[aria-label="Post"]',
            'div[role="button"]:has-text("Post")',
            'button:has-text("Post")',
            '[data-testid="react-composer-post-button"]',
        ]

        posted = False
        for selector in post_button_selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=3000):
                    await button.click()
                    posted = True
                    break
            except:
                continue

        if not posted:
            raise Exception("Could not find Post button")

        # Wait for post to complete
        await page.wait_for_timeout(3000)

        return {"success": True, "message": "Facebook post published successfully", "platform": platform}

    except Exception as e:
        error_msg = str(e)
        screenshot_path = await take_error_screenshot(page, platform, error_msg)
        return {
            "success": False,
            "message": f"Facebook posting failed: {error_msg}",
            "platform": platform,
            "screenshot": screenshot_path,
        }


async def post_instagram(page: Page, content: str) -> dict:
    """Post content to Instagram (text post/story or caption for existing draft)."""
    platform = "instagram"

    try:
        # Navigate to Instagram
        await page.goto(PLATFORM_URLS["instagram"], wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Click Create button (+ icon)
        create_selectors = [
            '[aria-label="New post"]',
            '[aria-label="Create"]',
            'svg[aria-label="New post"]',
            'a[href="/create/select/"]',
            '[role="link"]:has(svg[aria-label="New post"])',
        ]

        clicked = False
        for selector in create_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=3000):
                    await element.click()
                    clicked = True
                    break
            except:
                continue

        if not clicked:
            # Try clicking the side menu create option
            try:
                await page.locator('span:has-text("Create")').first.click()
                clicked = True
            except:
                raise Exception("Could not find Create button")

        await page.wait_for_timeout(2000)

        # For Instagram, we need to handle media upload first
        # This implementation assumes user has pre-staged content or is doing text story

        # Look for caption/text input area
        caption_selectors = [
            '[aria-label="Write a caption..."]',
            'textarea[aria-label*="caption"]',
            '[contenteditable="true"]',
            'textarea[placeholder*="caption"]',
        ]

        typed = False
        for selector in caption_selectors:
            try:
                editor = page.locator(selector).first
                if await editor.is_visible(timeout=5000):
                    await editor.click()
                    await page.keyboard.type(content, delay=30)
                    typed = True
                    break
            except:
                continue

        if not typed:
            # Instagram requires image/video - inform user
            raise Exception(
                "Instagram requires media upload. Please ensure you have media ready or use Instagram's native app for text-only posts."
            )

        await page.wait_for_timeout(1000)

        # Click Share button
        share_selectors = [
            'button:has-text("Share")',
            '[role="button"]:has-text("Share")',
            'div:has-text("Share"):not(:has(*))',
        ]

        shared = False
        for selector in share_selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=3000):
                    await button.click()
                    shared = True
                    break
            except:
                continue

        if not shared:
            raise Exception("Could not find Share button")

        await page.wait_for_timeout(3000)

        return {"success": True, "message": "Instagram post published successfully", "platform": platform}

    except Exception as e:
        error_msg = str(e)
        screenshot_path = await take_error_screenshot(page, platform, error_msg)
        return {
            "success": False,
            "message": f"Instagram posting failed: {error_msg}",
            "platform": platform,
            "screenshot": screenshot_path,
        }


async def post_twitter(page: Page, content: str) -> dict:
    """Post content to Twitter (X)."""
    platform = "twitter"

    try:
        # Navigate to Twitter home
        await page.goto(PLATFORM_URLS["twitter"], wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # Find the tweet composer
        composer_selectors = [
            '[data-testid="tweetTextarea_0"]',
            '[aria-label="Post text"]',
            '[data-testid="tweetTextarea_0RichTextInputContainer"]',
            'div[contenteditable="true"][aria-label*="Post"]',
            'div[contenteditable="true"][data-testid]',
        ]

        typed = False
        for selector in composer_selectors:
            try:
                editor = page.locator(selector).first
                if await editor.is_visible(timeout=3000):
                    await editor.click()
                    await page.keyboard.type(content, delay=30)
                    typed = True
                    break
            except:
                continue

        if not typed:
            raise Exception("Could not find tweet composer")

        await page.wait_for_timeout(1000)

        # Click Post button
        post_button_selectors = [
            '[data-testid="tweetButtonInline"]',
            '[data-testid="tweetButton"]',
            'button:has-text("Post")',
            '[role="button"]:has-text("Post")',
        ]

        posted = False
        for selector in post_button_selectors:
            try:
                button = page.locator(selector).first
                if await button.is_visible(timeout=3000):
                    await button.click()
                    posted = True
                    break
            except:
                continue

        if not posted:
            raise Exception("Could not find Post button")

        # Wait for success
        await page.wait_for_timeout(3000)

        # Check for success indicator
        try:
            success = await page.locator('text="Your post was sent"').is_visible(timeout=2000)
        except:
            pass

        return {"success": True, "message": "Twitter post published successfully", "platform": platform}

    except Exception as e:
        error_msg = str(e)
        screenshot_path = await take_error_screenshot(page, platform, error_msg)
        return {
            "success": False,
            "message": f"Twitter posting failed: {error_msg}",
            "platform": platform,
            "screenshot": screenshot_path,
        }


async def execute_post(markdown_file: str) -> dict:
    """Main function to execute social media posting."""
    ensure_directories()

    # Parse the markdown file
    try:
        metadata = parse_markdown_file(markdown_file)
    except Exception as e:
        return {"success": False, "message": f"Failed to parse markdown file: {e}"}

    platform = metadata.get("platform", "").lower()
    content = metadata.get("content", "")

    if not platform:
        return {"success": False, "message": "No platform specified in markdown file"}

    if not content:
        return {"success": False, "message": "No content specified in markdown file"}

    if platform not in PLATFORM_URLS:
        return {"success": False, "message": f"Unsupported platform: {platform}. Supported: {list(PLATFORM_URLS.keys())}"}

    # Platform-specific posting functions
    platform_handlers = {
        "linkedin": post_linkedin,
        "facebook": post_facebook,
        "instagram": post_instagram,
        "twitter": post_twitter,
    }

    async with async_playwright() as p:
        # Launch persistent browser context
        context = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = await context.new_page()

        try:
            # Execute platform-specific posting
            handler = platform_handlers[platform]
            result = await handler(page, content)
        finally:
            await context.close()

        return result


async def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python social_media_executor_v2.py <markdown_file>")
        print("\nExample markdown file format:")
        print("---")
        print('platform: linkedin')
        print('content: "Your post content here"')
        print("---")
        sys.exit(1)

    markdown_file = sys.argv[1]

    if not os.path.exists(markdown_file):
        print(f"Error: File not found: {markdown_file}")
        sys.exit(1)

    print(f"Processing: {markdown_file}")
    result = await execute_post(markdown_file)

    if result["success"]:
        print(f"\n[SUCCESS] {result['message']}")
    else:
        print(f"\n[ERROR] {result['message']}")
        if "screenshot" in result:
            print(f"Screenshot saved: {result['screenshot']}")

    return result


if __name__ == "__main__":
    asyncio.run(main())
