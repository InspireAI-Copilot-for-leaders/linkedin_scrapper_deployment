import os
from scrapper import LinkedInScraper

def scrape_linkedin(request):
    # Get parameters from the request or environment variables
    profile_url = os.getenv('PROFILE_URL', 'https://www.linkedin.com/in/krishant-sethia-976a50174/')
    bucket_name = os.getenv('BUCKET_NAME', 'linkedin_scrapper_csv_files')

    scraper = LinkedInScraper(headless=True)
    user_posts = scraper.scrape_pipeline(profile_url, bucket_name)

    return f"Scraping completed. {len(user_posts)} posts scraped and saved to gs://{bucket_name}/"

if __name__ == "__main__":
    scrape_linkedin(None)