
import json
import re
import time
import queue
import threading
import copy
from bs4 import BeautifulSoup
from seleniumbase import Driver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException
 
BASE_URL = "https://www.ratemds.com"
NUM_WORKERS = 3
WAIT_TIMEOUT = 10
MAX_REVIEWS = 100
target_sections = [
    'Facility Affiliations',
    'Accepting New Patients',
    'Accepting Virtual Visits',
    'Biography',
    'Languages',
    'Education',
    'Other Specialties',
    'Areas of Expertise',
    'Awards & Recognitions',
    'Publications & Research'
]

def get_partner_reviews(soup):
    reviews = []

    review_containers = soup.find_all('span', id='partnerRatings')

    for container in review_containers:
        rating_div = container.find('div', class_='star-rating')
        rating = rating_div.get('title') if rating_div else None
        
        body_tag = container.find('p', class_='partner-review-body')
        body = body_tag.get_text(strip=True) if body_tag else ""
                
        date_tag = container.find('span', class_='rating-comment-created')
        date = date_tag.get_text(strip=True) if date_tag else ""
        
        reviews.append({
            "rating": rating,
            "body": body,
            "helpful_votes": None,
            "date": date
        })

    return reviews

def get_local_reviews(soup):
    reviews = []
    review_items = soup.find_all('div', class_='rating-proof-item')

    for item in review_items:        
        star_div = item.find('div', class_='star-rating')
        rating_score = star_div.get('title') if star_div else None
        
        body_tag = item.find('p', class_='reviewBody')
        body = body_tag.get_text(strip=True) if body_tag else None
        
        vote_link = item.find('a', class_='rating-proof-item__vote')
        vote_count = vote_link.find('span').get_text(strip=True) if vote_link and vote_link.find('span') else "0"
        
        date_tag = item.find('span', class_='rating-proof-item__date')
        post_date = date_tag.find('span').get_text(strip=True) if date_tag and date_tag.find('span') else None

        reviews.append({
            "rating": rating_score,
            "text": body,
            "helpful_votes": vote_count,
            "date": post_date
        })
    return reviews

def get_doctor_data(soup):
    data = {}
    dropdown_container = soup.find('ul', class_='ant-dropdown-menu')

    if dropdown_container:
        address_tags = dropdown_container.find_all('div', class_='card__content-container')
        
        address = {
            tag.find('div', class_='conversion-pack-row-location__title').get_text(strip=True): 
            tag.find('div', class_='address').get_text(strip=True) 
            for tag in address_tags
        }
    facilities = []
    location_cards = soup.find_all('div', class_='card--conversion-pack-row')
    
    for card in location_cards:
        link_tag = card.find('a', class_='conversion-pack-row-location__title')
        address_div = card.find('div', class_='address')
        
        if link_tag and address_div:
            name = link_tag.get_text(strip=True)
            href = link_tag.get('href')
            address = address_div.get_text(strip=True)
            
            facilities.append({
                "name": name,
                "url_handle": href,
                "address": address
            })
    
    data['facilities'] = facilities

    for div in soup.find_all('div'):
        h4 = div.find('h4')
        
        if h4 and h4.get_text(strip=True) in target_sections:
            section_name = h4.get_text(strip=True)
            
            if section_name == "Facility Affiliations":
                facilities_list = []
                
                hospital_divs = div.find_all('div', class_='widget-hospital')
                
                for hosp in hospital_divs:
                    name_div = hosp.find('div', class_='widget-name')
                    facility_text = name_div.get_text(strip=True) if name_div else None
                    
                    a_tag = hosp.find('a')
                    facility_href = a_tag.get('href') if a_tag else None
                    
                    if facility_text:
                        facilities_list.append({
                            "text": facility_text,
                            "href": facility_href
                        })
                
                data[section_name] = facilities_list
                    
            else:
                li_tags = div.find_all('li')
                if li_tags:
                    data[section_name] = [li.get_text(" ", strip=True) for li in li_tags]
                else:
                    div_copy = copy.copy(div)
                    if div_copy.find('h4'):
                        div_copy.find('h4').decompose()
                    data[section_name] = div_copy.get_text(" ", strip=True)

    plans = []
    provider_tags = soup.find_all('div', class_='insurance-provider')
    for tag in provider_tags:
        plan_name = tag.get_text(" ", strip=True) 
        plans.append(plan_name)

    data['insurance'] = plans
    return data

def process_tab_reviews(driver, tab_data_attr, next_href_substring, get_reviews_func, name):
    reviews_collected = []
 
    try:
        tab_element = driver.find_element(By.XPATH, f'//button[@data-tab="{tab_data_attr}"]')
        driver.execute_script("arguments[0].click();", tab_element)
        time.sleep(1.5)
    except Exception:
        print(f"   -> Tab '{tab_data_attr}' not found/clickable for {name}. Processing current view.")
 
    page_count = 0
    while len(reviews_collected) < 100:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        page_reviews = get_reviews_func(soup)
        if page_reviews:
            reviews_collected.extend(page_reviews)
 
        page_count += 1
 
        try:
            next_button = driver.find_element(
                By.XPATH, f'//a[@aria-label="Next page" and contains(@href, "{next_href_substring}")]'
            )
            parent_li = next_button.find_element(By.XPATH, './..')
 
            if "disabled" in parent_li.get_attribute("class"):
                break
 
            driver.execute_script("arguments[0].click();", next_button)
            time.sleep(1.5)
        except Exception:
            break
 
    return reviews_collected, page_count 

def get_doctor(driver, card):
    doctor = {}
 
    name_tag = card.find("a", class_="search-item-doctor-name")
    name = doctor['name'] = name_tag.text.strip() if name_tag else None
    doctor['href'] = name_tag['href'] if name_tag else None
    if not name_tag or not doctor['href']:
        return None
 
    specialty_tag = card.find("a", class_="search-item-specialty-text")
    doctor['specialty'] = specialty_tag.text.strip() if specialty_tag else None
 
    profile_url = BASE_URL + doctor['href']
 
    driver.uc_open(profile_url)
    time.sleep(1.5)
 
    inner = BeautifulSoup(driver.page_source, 'html.parser')
    doctor['data'] = get_doctor_data(inner)
 
    all_reviews = []
 
    native_reviews, native_pages = process_tab_reviews(
        driver, "ratemds", "?page=", get_local_reviews, name
    )
    all_reviews.extend(native_reviews)
    print(f"   -> [{threading.current_thread().name}] {len(native_reviews)} native reviews ({native_pages} pages) - {name}")
 
    partner_reviews, partner_pages = process_tab_reviews(
        driver, "partners", "?third_party_page=", get_partner_reviews, name
    )
    all_reviews.extend(partner_reviews)
    print(f"   -> [{threading.current_thread().name}] {len(partner_reviews)} partner reviews ({partner_pages} pages) - {name}")
 
    doctor['reviews'] = all_reviews
    print(f"[{threading.current_thread().name}] Done: {name} ({len(all_reviews)} total reviews)")
    return doctor
 

def make_driver():
    d = Driver(
        uc=True,
        headless=False,
        chromium_arg="--disable-dev-shm-usage,--no-sandbox",
    )
    d.set_window_size(1200, 900)
    return d
 
 
def is_driver_alive(driver):
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False
 

def worker_loop(worker_id, card_queue, write_lock, output_path):
    driver = make_driver()
    processed = 0
 
    try:
        while True:
            try:
                card = card_queue.get_nowait()
            except queue.Empty:
                break
 
            name_tag = card.find("a", class_="search-item-doctor-name")
            name = name_tag.text.strip() if name_tag else "unknown"
 
            try:
                result = get_doctor(driver, card)
            except Exception as e:
                if is_driver_alive(driver):
                    print(f"[worker-{worker_id}] Error scraping '{name}' (browser still OK, skipping this doctor): {e}")
                    result = None
                else:
                    print(f"[worker-{worker_id}] Browser session died on '{name}', restarting: {e}")
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = make_driver()
                    result = None
 
            if result:
                with write_lock:
                    with open(output_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(result) + "\n")
                processed += 1
 
            card_queue.task_done()
    finally:
        try:
            driver.quit()
        except Exception:
            pass
        print(f"[worker-{worker_id}] Finished. Processed {processed} doctors.")
 
 
def scrape_page(lister_driver, num):
    print(f'Scraping page {num}')
    lister_driver.uc_open(BASE_URL + '/best-doctors/' + (f'?page={num}' if num > 1 else ''))
    time.sleep(3)
 
    soup = BeautifulSoup(lister_driver.page_source, 'html.parser')
    cards = soup.find_all("div", class_="doctor-profile-card")
    if not cards:
        print(f"No doctor cards found on page {num}.")
        return
 
    card_queue = queue.Queue()
    for card in cards:
        card_queue.put(card)
 
    write_lock = threading.Lock()
    workers = []
    for i in range(NUM_WORKERS):
        t = threading.Thread(
            target=worker_loop,
            args=(i, card_queue, write_lock, 'scraped_data.jsonl'),
            name=f"worker-{i}",
        )
        t.start()
        workers.append(t)
        time.sleep(1.0)  # stagger browser launches so they don't all hit Cloudflare at once
 
    for t in workers:
        t.join()
 
    print(f"--- Finished Search Page {num} ---")
 

if __name__ == "__main__":
    lister_driver = make_driver()
    try:
        for page_num in range(100, 101):
            scrape_page(lister_driver, page_num)
    finally:
        lister_driver.quit()
