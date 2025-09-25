from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import csv
import html
import re

# ----------------- helpers -----------------
AMT_RE = re.compile(r"[\d,]+(?:\.\d+)?")

def parse_amount(text):
    """Return integer rupee amount from strings like '₹ 1,04,999.00' or '1,04,999'."""
    if not text:
        return None
    # normalize text
    t = text.replace("₹", "").replace("Rs.", "").replace("Rs", "")
    m = AMT_RE.search(t)
    if not m:
        return None
    s = m.group(0).replace(",", "")
    try:
        # return integer rupees
        return int(float(s))
    except:
        return None

def extract_prices_from_card(card):
    """
    Returns (discounted_amt_int_or_None, mrp_amt_int_or_None, discounted_text, mrp_text)
    Heuristics:
      1) Look for span.a-price > span.a-offscreen (displayed price(s))
      2) Look for span.a-text-price > span.a-offscreen (crossed-out price = MRP)
      3) If multiple a-offscreen prices found, assume min is discounted and max is mrp.
    """
    discounted_amt = None
    mrp_amt = None
    discounted_text = None
    mrp_text = None

    try:
        # Gather all a-offscreen spans (these often contain formatted prices)
        offscreen = card.find_elements(By.CSS_SELECTOR, "span.a-offscreen")
        off_texts = []
        for el in offscreen:
            txt = (el.get_attribute("textContent") or el.text or "").strip()
            if txt:
                off_texts.append(txt)

        # If we got some offscreen prices, parse them
        parsed = []
        for t in off_texts:
            a = parse_amount(t)
            if a is not None:
                parsed.append((a, t))

        if parsed:
            # sort by amount ascending
            parsed_sorted = sorted(parsed, key=lambda x: x[0])
            # assume smallest is displayed (discounted) and largest is original (mrp) when multiple values appear
            discounted_amt, discounted_text = parsed_sorted[0]
            if len(parsed_sorted) > 1:
                mrp_amt, mrp_text = parsed_sorted[-1]
            # return early if we have at least discounted
            if discounted_amt:
                return discounted_amt, mrp_amt, discounted_text, mrp_text
    except Exception:
        pass

    # Try explicit crossed-out price selector for MRP
    try:
        mrp_el = card.find_elements(By.CSS_SELECTOR, "span.a-text-price > span.a-offscreen")
        if mrp_el:
            txt = (mrp_el[0].get_attribute("textContent") or mrp_el[0].text or "").strip()
            mrp_amt = parse_amount(txt)
            mrp_text = txt
    except:
        pass

    # Try single displayed price via a-price-whole + fraction
    try:
        whole = card.find_elements(By.CSS_SELECTOR, ".a-price-whole")
        frac = card.find_elements(By.CSS_SELECTOR, ".a-price-fraction")
        if whole:
            w = whole[0].text.strip()
            f = frac[0].text.strip() if frac else ""
            txt = w + (("." + f) if f else "")
            amount = parse_amount(txt)
            if amount:
                if discounted_amt is None:
                    discounted_amt = amount
                    discounted_text = txt
    except:
        pass

    # As a last fallback, try any element containing '₹' in the card
    if discounted_amt is None:
        try:
            el = card.find_element(By.XPATH, ".//*[contains(text(),'₹') or contains(text(),'Rs') or contains(text(),'INR')]")
            txt = (el.get_attribute("textContent") or el.text or "").strip()
            amt = parse_amount(txt)
            if amt:
                discounted_amt = amt
                discounted_text = txt
        except:
            pass

    return discounted_amt, mrp_amt, discounted_text, mrp_text

# ----------------- existing helpers (unchanged) -----------------
def extract_price_from_card(card):
    """Try several fallbacks to get a price string from a product card."""
    try:
        el = card.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen")
        txt = el.get_attribute("innerText").strip()
        if txt:
            return txt
    except:
        pass
    try:
        whole = card.find_element(By.CLASS_NAME, "a-price-whole").text.strip()
        frac = card.find_element(By.CLASS_NAME, "a-price-fraction").text.strip()
        return whole + "." + frac
    except:
        pass
    try:
        txt = card.text
        if "₹" in txt:
            i = txt.find("₹")
            return txt[i:i+15].splitlines()[0]
    except:
        pass
    return "N/A"

def close_common_popups(driver):
    """Best-effort to close cookie/location popups that block the page."""
    selectors = [
        "input#sp-cc-accept",
        "button#sp-cc-accept",
        "button[aria-label='Accept Cookies']",
        "button[data-action='a-popover-close']",
        "button.a-button-close",
    ]
    for sel in selectors:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for e in els:
                if e.is_displayed():
                    try:
                        e.click()
                        time.sleep(0.2)
                    except:
                        pass
        except:
            pass

def find_next_button(driver):
    """Return a clickable Next button element or (None, None) if not found."""
    selectors = [
        (By.CSS_SELECTOR, "ul.a-pagination li.a-last a"),
        (By.XPATH, "//a[contains(@class,'s-pagination-next')]"),
        (By.XPATH, "//a[@aria-label='Next']"),
        (By.XPATH, "//a[contains(text(),'Next')]"),
    ]
    for sel in selectors:
        try:
            el = driver.find_element(*sel)
            if el and el.is_displayed():
                return el, sel
        except:
            continue
    return None, None

def extract_title_and_link(card, debug=False):
    """
    Try several strategies to extract title text and product link from a product card.
    Returns (title, link) or (None, None) on failure.
    If debug=True returns (None, None, innerHTML) for troubleshooting.
    """
    # 1) h2 > a (common)
    try:
        h2 = card.find_element(By.TAG_NAME, "h2")
        a = h2.find_element(By.TAG_NAME, "a")
        link = a.get_attribute("href")
        title_text = a.text.strip() or a.get_attribute("aria-label") or None
        if title_text and link:
            return title_text, link
    except:
        pass

    # 2) anchors that point to /dp/ or contain sspa/click or gp
    try:
        anchors = card.find_elements(By.XPATH, ".//a[contains(@href,'/dp/') or contains(@href,'/gp/') or contains(@href,'sspa/click')]")
        for a in anchors:
            link = a.get_attribute("href")
            title_text = a.text.strip() or a.get_attribute("aria-label") or None
            if title_text and link:
                return title_text, link
            if not title_text and link:
                aria = a.get_attribute("aria-label")
                if aria:
                    return aria.strip(), link
    except:
        pass

    # 3) image alt text
    try:
        img = card.find_element(By.XPATH, ".//img[@alt]")
        alt = img.get_attribute("alt").strip()
        try:
            ancestor_a = img.find_element(By.XPATH, "ancestor::a[1]")
            link = ancestor_a.get_attribute("href")
            if alt and link:
                return alt, link
        except:
            if alt:
                return alt, None
    except:
        pass

    # 4) any anchor with text
    try:
        a_any = card.find_element(By.XPATH, ".//a[string-length(normalize-space(text()))>0]")
        link = a_any.get_attribute("href")
        title_text = a_any.text.strip() or a_any.get_attribute("aria-label") or None
        if title_text:
            return title_text, link
    except:
        pass

    if debug:
        try:
            return None, None, card.get_attribute("innerHTML")
        except:
            return None, None, "<no innerHTML available>"

    return None, None

# ----------------- main scraper -----------------
def scrape_amazon(query="headphones", min_results=120, max_pages=12, output_csv="amazon_headphones.csv", headless=False):
    """
    Scrape Amazon.in for `query` and save results to output_csv.
    Default is set for headphones.
    """
    options = Options()
    options.add_experimental_option("detach", True)  # keep browser open while debugging
    options.add_argument("--log-level=3")
    # use a realistic user agent
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
    if headless:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 12)

    try:
        driver.get("https://www.amazon.in")
        time.sleep(1)
        close_common_popups(driver)

        search_box = wait.until(EC.presence_of_element_located((By.ID, "twotabsearchtextbox")))
        search_box.clear()
        search_box.send_keys(query)
        search_box.send_keys(Keys.RETURN)
        time.sleep(2)
        close_common_popups(driver)

        results = []
        pages_visited = 0
        debug_failures = 0

        while len(results) < min_results and pages_visited < max_pages:
            pages_visited += 1
            # help lazy loading of items
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.25);")
            time.sleep(0.6)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.0)

            product_cards = driver.find_elements(By.XPATH, '//div[@data-component-type="s-search-result"]')
            if not product_cards:
                product_cards = driver.find_elements(By.XPATH, '//*[@data-asin and @data-asin!=""]')

            print(f"[INFO] Page {pages_visited}: found {len(product_cards)} product cards; collected so far: {len(results)}")

            for card in product_cards:
                if len(results) >= min_results:
                    break
                try:
                    title, link = extract_title_and_link(card)
                    if not title and not link and debug_failures < 3:
                        debug_failures += 1
                        t, l, inner = extract_title_and_link(card, debug=True)
                        print("[DEBUG] sample failed card innerHTML snippet:")
                        print(html.escape(inner)[:1500])
                        continue

                    if title and not link:
                        try:
                            a = card.find_element(By.XPATH, ".//a[contains(@href,'/dp/') or contains(@href,'/gp/') or contains(@href,'/product') or contains(@href,'sspa/click')]")
                            link = a.get_attribute("href")
                        except:
                            link = None

                    if not title:
                        continue

                    # get displayed price string (for compatibility) - still kept in results for backwards compat
                    price = extract_price_from_card(card)

                    # --- NEW: extract discounted price and mrp ---
                    discounted_amt, mrp_amt, discounted_txt, mrp_txt = extract_prices_from_card(card)

                    # compute discount percentage if both present
                    discount_percentage = ""
                    if mrp_amt and discounted_amt:
                        try:
                            discount_percentage = round(((mrp_amt - discounted_amt) / mrp_amt) * 100, 2)
                        except:
                            discount_percentage = ""

                    # dedupe by link or title
                    if link:
                        if any(r.get("link") == link for r in results):
                            continue
                    else:
                        if any(r.get("title") == title for r in results):
                            continue

                    results.append({
                        "title": title,
                        "price": price,
                        "link": link,
                        "mrp": mrp_amt if mrp_amt is not None else "",
                        "discount_percentage": discount_percentage
                    })
                    print(f"[ADD] {len(results)}: {title} | price={price} | mrp={mrp_amt} | discount%={discount_percentage}")
                except Exception as e:
                    print("[WARN] card parse error:", str(e)[:200])
                    continue

            if len(results) >= min_results:
                break

            next_el, _ = find_next_button(driver)
            if not next_el:
                print("[INFO] No Next button found. Stopping pagination.")
                break

            try:
                prev_page_label = None
                try:
                    prev_page_label = driver.find_element(By.CSS_SELECTOR, "ul.a-pagination li.a-selected").text
                except:
                    prev_page_label = None

                driver.execute_script("arguments[0].scrollIntoView(true);", next_el)
                time.sleep(0.3)
                next_el.click()

                if prev_page_label:
                    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "ul.a-pagination li.a-selected").text != prev_page_label)
                else:
                    wait.until(EC.presence_of_element_located((By.XPATH, '//div[@data-component-type="s-search-result"]')))
                time.sleep(1.0)
            except Exception as e:
                print("[WARN] Pagination error or page did not change:", e)
                time.sleep(2)
                if not driver.find_elements(By.XPATH, '//div[@data-component-type="s-search-result"]'):
                    print("[INFO] No product cards after clicking Next — stopping.")
                    break

        # Save to CSV
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "price", "link", "mrp", "discount_percentage"])
            writer.writeheader()
            for row in results:
                writer.writerow(row)

        print(f"✅ Saved results to {output_csv} (total {len(results)} items)")
        return results

    finally:
        # close driver for real now
        try:
            driver.quit()
        except:
            pass


if __name__ == "__main__":
    # scrape headphones and save to amazon_headphones.csv
    data = scrape_amazon(query="headphones", min_results=1000, max_pages=50, output_csv="amazon_headphones.csv", headless=False)

    # print a preview of the first 30 results
    print("\n📌 Preview (first 30 results):\n")
    for i, item in enumerate(data[:30], 1):
        print(f"{i}. {item['title']}\n   Price: {item['price']}\n   MRP: {item['mrp']}\n   Discount%: {item['discount_percentage']}\n   Link: {item['link']}\n{'-'*80}")
