# Importing Dependencies
import os
import io
import time
import logging
import warnings
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys  # For scrolling
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup as bs
from fake_useragent import UserAgent
from chromedriver_py import binary_path
import re
import csv
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import urllib3
from google.cloud import storage
from webdriver_manager.chrome import ChromeDriverManager


# Suppress warnings
warnings.filterwarnings("ignore")

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Suppress the specific warning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)

# Load Environment Variables
load_dotenv()

class LinkedInScraper:
    def __init__(self, headless=True):
        self.email = os.getenv('LINKEDIN_EMAIL')
        self.password = os.getenv('LINKEDIN_PASSWORD')
        self.source_url = "https://www.linkedin.com/login"
        

        # self.email = "anonymous6353@gmail.com"
        # self.password = "linkedin_scrapper"
        

        self.headless = headless
        self.ua = UserAgent()
        self.driver = None
        #self.service = webdriver.ChromeService(executable_path=binary_path)
        #self.service = ChromeService(ChromeDriverManager().install())
        self.service = ChromeService(executable_path='/usr/local/bin/chromedriver')

        # Increase max_scroll to load more posts
        self.max_scroll = 100
        self.scroll_pause_time = 0.5  # Reduced from 3 to 0.5 seconds
        self.user_page = None
        self.user_posts = []

    def setup_driver(self):
        """Setup Selenium WebDriver with options."""
        chrome_options = Options()
        chrome_options.add_argument(f'user-agent={self.ua.chrome}')
        chrome_options.add_argument("referer=https://www.google.com/")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("window-size=1920,1080")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
    
        if self.headless:
            chrome_options.add_argument("--headless=new")
            logging.info("Headless Chrome Initialized")
        else:
            logging.info("Chrome Initialized")

        #self.driver = webdriver.Chrome(service=self.service, options=chrome_options)
        self.driver = webdriver.Chrome(service=self.service,options=chrome_options)
        self.driver.set_page_load_timeout(60)
        self.driver.set_script_timeout(60)
        self.driver.execute_cdp_cmd("Page.enable", {})
        self.driver.execute_cdp_cmd("Network.enable", {})
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            })
            """
        })

    def cleanup(self):
        """Clean up by quitting the driver."""
        if self.driver:
            self.driver.quit()
            logging.info("WebDriver closed.")
        

    def login(self):
        """Log in to LinkedIn using provided credentials."""
        try:
            self.driver.get(self.source_url)
            
            # Increase timeout duration
            timeout = 10
            
            # Wait for the username field to be present and visible
            username = WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((By.ID, "username"))
            )
            username.send_keys(self.email)
            
            # Wait for the password field to be present and visible
            password = WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located((By.ID, "password"))
            )
            password.send_keys(self.password)
            
            # Wait for the login button to be present and visible
            login = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']"))
            )
            login.click()

            logging.info("Logged in successfully")

            
        except Exception as e:
            logging.error(f"Error in logging in: {e}")
            self.cleanup()
            raise e

    def load_profile_page(self, profile_url):
        """Load the LinkedIn profile page's 'recent activity' section."""
        try:

            profile_posts_url = profile_url.rstrip('/') + '/recent-activity/all/'
            logging.info(f"Loading profile page: {profile_posts_url}")
            self.driver.get(profile_posts_url)
            # Confirm that an expected element is present
            # WebDriverWait(self.driver, 30).until(
            #     EC.presence_of_element_located((By.CSS_SELECTOR, 'div.feed-shared-update-v2'))
            # )
            logging.info("Profile page loaded successfully")
        except Exception as e:
            logging.error(f"Error loading profile page: {e}")
            self.cleanup()
            raise e

    def scroll_to_bottom(self):
        """Scroll to the bottom of the page to load all posts."""
        SCROLL_COMMAND = "window.scrollTo(0, document.body.scrollHeight);"
        GET_SCROLL_HEIGHT_COMMAND = "return document.body.scrollHeight"

        try:

            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            last_height = self.driver.execute_script(GET_SCROLL_HEIGHT_COMMAND)
            scrolls = 0
            no_change_count = 0
            max_no_change_count = 5

            while True:
                self.driver.execute_script(SCROLL_COMMAND)
                time.sleep(self.scroll_pause_time)

                # Wait for posts to load
                self.wait_for_posts_to_load()

                new_height = self.driver.execute_script(GET_SCROLL_HEIGHT_COMMAND)

                if new_height == last_height:
                    no_change_count += 1
                else:
                    no_change_count = 0

                if no_change_count >= max_no_change_count:
                    logging.info("Reached the bottom of the page or no new content is loading.")
                    break

                last_height = new_height
                scrolls += 1
                logging.info(f"Scroll attempt: {scrolls}, Current height: {new_height}")

        except Exception as e:
            logging.error(f"Error in scrolling: {e}")
            self.cleanup()

    def wait_for_posts_to_load(self):
        """Waits for the posts to load after scrolling."""
        try:
            # Wait for the last post container to load
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, 'li.profile-creator-shared-feed-update__container:last-child')))
        except Exception as e:
            logging.error(f"Error waiting for posts to load: {e}")

    def convert_relative_time(self, relative_time_str, current_time):
        """
        Converts a relative time string like '5h', '2d', '1w', '3mo', '1y' to an absolute datetime object.
        Returns a datetime object.
        """
        try:
            match = re.match(r'(\d+)([a-zA-Z]+)', relative_time_str)
            if not match:
                # If no match, try to parse it as a date string directly
                # For example, 'August 25, 2023'
                try:
                    return datetime.strptime(relative_time_str, '%B %d, %Y')
                except ValueError:
                    return current_time  # default to current time if parsing fails
            quantity = int(match.group(1))
            unit = match.group(2).lower()
            if unit in ['h', 'hr', 'hrs']:
                delta = timedelta(hours=quantity)
                post_time = current_time - delta
                # Include exact time for hours
                return post_time
            else:
                if unit in ['d', 'day', 'days']:
                    delta = timedelta(days=quantity)
                elif unit in ['w', 'wk', 'wks']:
                    delta = timedelta(weeks=quantity)
                elif unit in ['mo', 'mos', 'month', 'months']:
                    # For months, approximate as 30 days per month
                    delta = timedelta(days=30 * quantity)
                elif unit in ['y', 'yr', 'yrs']:
                    # For years, approximate as 365 days per year
                    delta = timedelta(days=365 * quantity)
                else:
                    # Unknown unit, return current time
                    return current_time
                post_date = current_time - delta
                # Set time to 9 am for days, weeks, months, years
                post_date = post_date.replace(hour=9, minute=0, second=0, microsecond=0)
                return post_date
        except Exception as e:
            logging.error(f"Error in converting relative time: {e}")
            return current_time  # default to current time if error occurs

    def extract_post_data(self, container_html, scrape_time):
        """Extract data from a single post container."""
        soup = bs(container_html, 'html.parser')

        # Initialize post structure
        post_structure = {
            "text": None,
            "type_of_post": None,
            "likes": 0,
            "comments": 0,
            "shares": 0
        }

        # Extract post text
        try:
            text_span = soup.find('div', class_='feed-shared-update-v2__description-wrapper').find('span', class_='break-words')
            if not text_span:
                return None  # Skip if text is not found
            for br in text_span.find_all("br"):
                br.replace_with("\n")
            post_structure["text"] = text_span.text.strip()
        except Exception as e:
            logging.error(f"Error in extracting post text: {e}")
            post_structure["text"] = None
            return None  # Skip if text extraction fails

        # Extract the type of post
        try:
            if soup.find('div', class_='update-components-image') is not None:
                post_structure['type_of_post'] = 'Image'
            elif soup.find('div', class_='update-components-video') is not None or soup.find('div', class_='update-components-linkedin-video') is not None:
                post_structure['type_of_post'] =  'Video'
            elif soup.find('div', class_='feed-shared-external-video__meta') is not None:
                post_structure['type_of_post'] = 'External Video'
            elif soup.find('article', class_='update-components-article') is not None:
                post_structure['type_of_post'] = 'Article'
            elif soup.find('div', class_='feed-shared-mini-update-v2 feed-shared-update-v2__update-content-wrapper artdeco-card') is not None:
                post_structure['type_of_post'] = 'Shared Post'
            else:
                post_structure['type_of_post'] = 'Text'
        except Exception as e:
            logging.error(f"Error in extracting post type: {e}")
            post_structure['type_of_post'] = 'Text'

        # Extract post date
        try:
            # Locate the actor container
            actor_container = soup.find('div', class_=re.compile('update-components-actor__container'))
            # Find the date element
            date_element = actor_container.find('span', class_=re.compile('update-components-actor__sub-description'))
            # Extract the date text
            post_date_raw = date_element.get_text(strip=True)
            # Clean up the date string
            post_date_text = post_date_raw.split('•')[0].strip()
            # Convert relative time to absolute date
            post_date = self.convert_relative_time(post_date_text, scrape_time)
            # Format the date as 'dd:mm:yyyy HH:MM'
            post_structure["date"] = post_date.strftime('%d-%m-%Y %H:%M')
        except Exception as e:
            logging.error(f"Error in extracting post date: {e}")
            post_structure["date"] = None

        # Check if the post is a repost
        try:
            # Look for the header text that indicates a repost
            header_container = soup.find('div', class_=re.compile('update-components-header.*'))
            header_text_span = header_container.find('span', class_=re.compile('update-components-header__text-view'))
            if header_text_span and 'reposted this' in header_text_span.text.strip().lower():
                post_structure['is_repost'] = True
                logging.info("Post is a repost")
            else:
                post_structure['is_repost'] = False
        except Exception as e:
            # logging.error(f"Error in determining if post is a repost: {e}")
            post_structure['is_repost'] = False

        # Extract reactions
        try:
            reaction_container = soup.find('div', class_='social-details-social-counts').text.split('\n')
            reactions = []
            for reaction in reaction_container:
                if reaction.strip() != '':
                    reactions.append(reaction.strip())

            # Extract likes, comments, shares
            post_likes, post_comments, post_shares = 0, 0, 0
            for i in reactions:
                if 'comment' in i:
                    post_comments = i.split(' ')[0]
                elif 'repost' in i or 'share' in i:
                    post_shares = i.split(' ')[0]
                else:
                    post_likes = i

            post_structure["likes"] = post_likes
            post_structure["comments"] = post_comments
            post_structure["shares"] = post_shares
        except Exception as e:
            logging.error(f"Error in extracting reactions: {e}")
            post_structure["likes"] = 0
            post_structure["comments"] = 0
            post_structure["shares"] = 0

        return post_structure

    def scrape_data(self):
        scrape_time = datetime.now()
        """Scrape posts from the LinkedIn profile's activity page."""
        try:
            # Get all the post containers using Selenium
            containers = self.driver.find_elements(By.CSS_SELECTOR, 'li.profile-creator-shared-feed-update__container')
            logging.info(f"Total post containers found: {len(containers)}")

            def process_container(container):
                # Scroll the container into view
                self.driver.execute_script("arguments[0].scrollIntoView(true);", container)
                # Wait for the container to load
                time.sleep(0.1)  # Reduced wait time

                # Now parse the container's outer HTML with BeautifulSoup
                container_html = container.get_attribute('outerHTML')

                # Extract post data
                post_data = self.extract_post_data(container_html, scrape_time)
                return post_data

            # Use ThreadPoolExecutor for parallel processing
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(process_container, container) for container in containers]
                for future in futures:
                    post_data = future.result()
                    if post_data:
                        self.user_posts.append(post_data)

        except Exception as e:
            logging.error(f"Error in scraping posts: {e}")
            return []
        
    def make_csv(self, profile_url, author_name, csv_filename):
        """Save scraped data to a CSV file."""
        try:
            with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                # Write header
                writer.writerow(["profile_url", "author_name", "post_content", "likes", "comments", "shares", "type_of_post", "is_repost", "time_of_posting"])
                
                # Write data rows
                for post in self.user_posts:
                    writer.writerow([
                        profile_url,
                        author_name,
                        post.get("text", ""),
                        post.get("likes", 0),
                        post.get("comments", 0),
                        post.get("shares", 0),
                        post.get("type_of_post", ""),
                        post.get("is_repost", False),
                        post.get("date", "")
                    ])
            logging.info(f"Data saved to {csv_filename}")
        except Exception as e:
            logging.error(f"Error saving data to CSV: {e}")

    def save_to_cloud_storage(self, profile_url, author_name, bucket_name):
        """Save scraped data to a CSV file in Google Cloud Storage."""
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "cloud_storage_key.json"

            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)

            author_name_match = re.search(r'linkedin\.com/in/([^/]+)', profile_url)
            author_name = author_name_match.group(1) if author_name_match else "unknown"
            total_posts_scraped = len(self.user_posts)
            blob_name = f"{author_name}_{total_posts_scraped}.csv"
            blob = bucket.blob(blob_name)

            csv_content = io.StringIO()
            writer = csv.writer(csv_content)
            # Write header
            writer.writerow(["profile_url", "author_name", "post_content", "likes", "comments", "shares", "type_of_post", "is_repost", "time_of_posting"])
            
            # Write data rows
            for post in self.user_posts:
                writer.writerow([
                    profile_url,
                    author_name,
                    post.get("text", ""),
                    post.get("likes", 0),
                    post.get("comments", 0),
                    post.get("shares", 0),
                    post.get("type_of_post", ""),
                    post.get("is_repost", False),
                    post.get("date", "")
                ])

            blob.upload_from_string(csv_content.getvalue(), content_type="text/csv")
            logging.info(f"Data saved to gs://{bucket_name}/{blob_name}")
        except Exception as e:
                logging.error(f"Error saving data to Google Cloud Storage: {e}")



    def scrape_pipeline(self, profile_url, bucket_name):
        """Main function to orchestrate scraping."""
        try:
            self.setup_driver()
            self.login()
            self.load_profile_page(profile_url)
            self.scroll_to_bottom()
            self.scrape_data()

            # Save data to Google Cloud Storage
            self.save_to_cloud_storage(profile_url, "unknown", bucket_name)

            return self.user_posts
        finally:
            self.cleanup()

# # Example Usage
# if __name__ == "__main__":
#     # profile_url = "https://www.linkedin.com/in/krishant-sethia-976a50174/"
#     # bucket_name = "linkedin_scrapper_csv_files"

#     profile_url = os.getenv('PROFILE_URL', 'https://www.linkedin.com/in/krishant-sethia-976a50174/')
#     bucket_name = "linkedin_scrapper_csv_files"


#     scraper = LinkedInScraper(headless=True)
#     user_posts = scraper.scrape_pipeline(profile_url, bucket_name)