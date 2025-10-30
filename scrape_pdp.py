import csv
import re
import json
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException, ElementClickInterceptedException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys

TARGET_URL = "https://www.hollisterco.com/shop/wd/p/faux-fur-trim-puffer-bomber-jacket-61001859?faceout=model&seq=02&pagefm=navigation-grid&prodvm=navigation-grid"
OUTPUT_CSV = "variations.csv"
WAIT_SEC = 20

@dataclass
class Row:
    item_name: str
    merchant_supplied_id: str
    variant_id: str
    variation_name: str
    variance: str
    size_variance: str
    price: str
    sale_price: str
    in_stock_rate: str
    photo_url: str
    product_description: str

def wait_css(driver, css, sec=WAIT_SEC):
    return WebDriverWait(driver, sec).until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

def wait_visible(driver, css, sec=WAIT_SEC):
    return WebDriverWait(driver, sec).until(EC.visibility_of_element_located((By.CSS_SELECTOR, css)))

def safe_text(el) -> str:
    try:
        return (el.text or "").strip()
    except:
        return ""

def scroll_into_view(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)

def click_js(driver, el):
    driver.execute_script("arguments[0].click();", el)

def get_item_name_and_price(driver) -> Tuple[str, str, str]:
    """Wait until product name & price are really rendered"""
    item_name = ""
    price = ""
    sale_price = ""

    # try 3 times with small scrolls (Hollister lazy-renders)
    for _ in range(3):
        try:
            driver.execute_script("window.scrollTo(0, 300);")
            name_el = WebDriverWait(driver, WAIT_SEC).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'h1[data-testid="main-product-name"]'))
            )
            item_name = name_el.get_attribute("innerText").strip()
            if item_name:
                break
            time.sleep(1)
        except TimeoutException:
            time.sleep(1)

    if not item_name:
        item_name = driver.title.split("|")[0].strip()

    # price blocks
    try:
        price_el = WebDriverWait(driver, WAIT_SEC).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".product-price-text"))
        )
        price = price_el.text.strip()
    except TimeoutException:
        price = ""

    return item_name, price, sale_price


def get_all_colors(driver) -> List[Dict]:
    # Each color radio input + its img alt (color name)
    swatch_sections = driver.find_elements(By.CSS_SELECTOR, 'section[data-testid="swatch-group"] .swtg-input-inner-wrapper')
    colors = []
    for sec in swatch_sections:
        try:
            radio = sec.find_element(By.CSS_SELECTOR, 'input.swtg-input')
            # color name from sibling img alt
            color_img = sec.find_element(By.CSS_SELECTOR, 'img[alt]')
            color_name = color_img.get_attribute('alt').strip()
            colors.append({
                "wrapper": sec,
                "radio": radio,
                "value": radio.get_attribute("value"),
                "id": radio.get_attribute("id"),
                "name": color_name
            })
        except Exception:
            continue
    return colors

def get_current_color_product_id(color_dict):
    """
    From your color dict (built in get_all_colors), use the radio value (e.g., '61002405').
    """
    try:
        return color_dict.get("value") or ""
    except Exception:
        return ""

def select_color(driver, radio_el):
    # Click robustly
    try:
        scroll_into_view(driver, radio_el)
        click_js(driver, radio_el)
    except ElementClickInterceptedException:
        click_js(driver, radio_el)
    # wait for gallery/price to refresh (small sleep + wait on something stable)
    time.sleep(0.6)
    # wait until the selected radio has 'checked' attribute
    WebDriverWait(driver, WAIT_SEC).until(lambda d: radio_el.get_attribute('checked') is not None)

def get_first_image_src_for_current_color(driver) -> str:
    try:
        # first image inside product-page-images-mfe
        first_img = wait_visible(driver, 'section.product-page-images-mfe .product-page-gallery-mfe img')
        return first_img.get_attribute('src').strip()
    except TimeoutException:
        return ""

def open_details_and_material(driver):
    # Scroll near the accordion and open it if collapsed
    try:
        trigger_btn = wait_css(driver, '#details-accordion')
        scroll_into_view(driver, trigger_btn)
        # If not expanded, click
        expanded = trigger_btn.get_attribute("aria-expanded")
        if expanded == "false":
            click_js(driver, trigger_btn)
            # wait panel to become visible
            WebDriverWait(driver, WAIT_SEC).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, '#details-accordion-panel-id .accordion-panel-content'))
            )
        else:
            # already expanded – still ensure content visible
            wait_visible(driver, '#details-accordion-panel-id .accordion-panel-content')
    except Exception:
        pass

def get_variant_id_for_current_color(driver) -> str:
    open_details_and_material(driver)
    try:
        store = wait_css(driver, '.details-accordion-mfe__store-item-number span:last-child')
        return store.text.strip()
    except TimeoutException:
        return ""

def get_description_once(driver) -> str:
    open_details_and_material(driver)
    try:
        desc = wait_css(driver, '.details-accordion-mfe__description')
        return desc.text.strip()
    except TimeoutException:
        return ""

def get_sizes(driver) -> List[Dict]:
    # All size tiles; even unavailable should appear so we can still enumerate
    tiles = driver.find_elements(By.CSS_SELECTOR, '.size-tile-group [data-testid="sitg-input-inner-wrapper"]')
    sizes = []
    for t in tiles:
        try:
            input_el = t.find_element(By.CSS_SELECTOR, 'input.sitg-input')
            label = t.find_element(By.CSS_SELECTOR, '.sitg-label-text').text.strip()
            # Unavailable might be indicated by data-variant="unavailable" on wrapper OR a class/state
            unavailable = (t.get_attribute('data-variant') == 'unavailable')
            sizes.append({
                "wrapper": t,
                "input": input_el,
                "size": label,
                "unavailable": unavailable
            })
        except Exception:
            continue
    return sizes

def select_size(driver, input_el):
    try:
        scroll_into_view(driver, input_el)
        click_js(driver, input_el)
        WebDriverWait(driver, WAIT_SEC).until(lambda d: input_el.get_attribute('checked') is not None)
    except Exception:
        # Fallback: set checked via JS and dispatch events so page updates merchant id if needed
        driver.execute_script("""
            const el = arguments[0];
            el.checked = true;
            el.dispatchEvent(new Event('input', {bubbles:true}));
            el.dispatchEvent(new Event('change', {bubbles:true}));
        """, input_el)
        time.sleep(0.4)
        
def _read_window_states(driver):
    """Collect relevant window blobs: APOLLO_*, productPrices, productCatalog."""
    try:
        blobs = driver.execute_script("""
            const out = {};
            for (const k of Object.keys(window)) {
                if (k.startsWith('APOLLO_STATE__')) {
                    try { out[k] = String(window[k]); } catch(e){}
                }
            }
            out['productPrices'] = (typeof window.productPrices === 'string' || typeof window.productPrices === 'object')
                ? window.productPrices : null;
            out['productCatalog'] = (typeof window.productCatalog === 'string' || typeof window.productCatalog === 'object')
                ? window.productCatalog : null;
            return out;
        """)
        return blobs or {}
    except Exception:
        return {}

_SIZE_ORDER = ["XXS","XS","S","M","L","XL","XXL"]

def _norm(s):
    return (s or "").strip().lower()

def _extract_merchant_from_apollo(blobs_text, color_name, size_name, color_pid=None):
    """
    Try to find a 9-digit id near color+size inside APOLLO cache blobs.
    blobs_text: one big string combining APOLLO_* values.
    """
    c = re.escape(_norm(color_name))
    sz = re.escape(size_name)
    
    # Try with color name first (normalized: remove spaces in blobs too)
    text = blobs_text.lower().replace(" ", "")
    
    # window blobs often have "... size":"M" ... 663776651 ..." or vice-versa
    pat = re.compile(rf'(6\d{{8}}).{{0,200}}(?:size["\']?\s*[:=]\s*["\']?{sz}["\']?)', re.I|re.S)
    
    for m in pat.finditer(text):
        # if color given, ensure the same neighborhood mentions it
        start = max(0, m.start()-250)
        end = min(len(text), m.end()+250)
        seg = text[start:end]
        if c in seg or (color_pid and str(color_pid) in seg):
            return m.group(1)

    # reverse order (size then id)
    pat2 = re.compile(rf'(?:size["\']?\s*[:=]\s*["\']?{sz}["\']?).{{0,200}}(6\d{{8}})', re.I|re.S)
    for m in pat2.finditer(text):
        start = max(0, m.start()-250)
        end = min(len(text), m.end()+250)
        seg = text[start:end]
        if c in seg or (color_pid and str(color_pid) in seg):
            return m.group(1)

    return ""

def _extract_merchant_from_productPrices(productPrices, color_product_id, size_name):
    """
    Fallback: productPrices is a JSON string mapping color_product_id -> items dict keyed by 9-digit merchant ids.
    We attempt to pick the merchant id by size order index.
    """
    try:
        if isinstance(productPrices, str):
            pp = json.loads(productPrices)
        else:
            pp = productPrices
        color_key = str(color_product_id)
        node = pp.get(color_key) or {}
        items = node.get("items") or {}
        # Preserve JSON order if possible (Python 3.7+ keeps dict insertion order)
        ids = list(items.keys())
        # map size to index by our known order
        idx = _SIZE_ORDER.index(size_name) if size_name in _SIZE_ORDER else 0
        if ids:
            # clamp idx to range
            idx = max(0, min(idx, len(ids)-1))
            return ids[idx]
        return ""
    except Exception:
        return ""

def get_merchant_supplied_id_smart(driver, color_name, size_name, color_product_id=None):
    """
    Master resolver:
      1) scan APOLLO_STATE__ blobs (GraphQL cache) for color+size -> 9-digit match
      2) fallback to productPrices[color_pid].items ordered by size sequence
    """
    blobs = _read_window_states(driver)
    # combine APOLLO blobs into one big string
    apollo_text = " ".join([v for k,v in blobs.items() if k.startswith("APOLLO_STATE__") and isinstance(v, str)])
    mid = _extract_merchant_from_apollo(apollo_text, color_name, size_name, color_pid=color_product_id)
    if mid:
        return mid

    # fallback: productPrices
    pp = blobs.get("productPrices")
    if pp:
        return _extract_merchant_from_productPrices(pp, color_product_id, size_name)

    return ""

def get_merchant_supplied_id(driver) -> str:
    # Inside product-rating-container → [data-bv-product-id]
    try:
        container = wait_css(driver, '.product-rating-container [data-bv-product-id]')
        return container.get_attribute('data-bv-product-id').strip()
    except TimeoutException:
        return ""

def get_stock_state(size_dict) -> str:
    # Map to requested strings
    if size_dict.get("unavailable"):
        return "Unavailable"
    # Site often uses backorderable wording when selectable but not instant in-stock. We'll default to Backorderable for selectable sizes.
    return "Backorderable"

def main():
    options = uc.ChromeOptions()
  # options.add_argument("--headless=new")  # headless; remove this line if you want to watch the browser
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = uc.Chrome(options=options)
    driver.set_page_load_timeout(120)

    rows: List[Row] = []
    try:
        driver.get(TARGET_URL)
        time.sleep(5)  # give React time to render main content

        # Ensure key sections present
        wait_css(driver, 'h1[data-testid="main-product-name"]')
        wait_css(driver, 'section.product-page-images-mfe')
        wait_css(driver, 'section[data-testid="swatch-group"]')
        wait_css(driver, '.size-tile-group')

        item_name, price_text, sale_text = get_item_name_and_price(driver)

        # Get static description once per product (we'll refresh after first color click if needed)
        product_description = get_description_once(driver)  # may be empty until we first open; handled later

        colors = get_all_colors(driver)
        if not colors:
            raise RuntimeError("No colors detected.")

        for c_idx, color in enumerate(colors):
            # Select color
            select_color(driver, color["radio"])

            # Refresh page anchors for this state
            photo_url = get_first_image_src_for_current_color(driver)
            variant_id = get_variant_id_for_current_color(driver)
            if not product_description:
                product_description = get_description_once(driver)

            sizes = get_sizes(driver)
            for s in sizes:
                # we still want a row even if unavailable
                if not s["unavailable"]:
                    select_size(driver, s["input"])
                else:
                    # Try to select anyway (site often allows clicking even when marked unavailable)
                    try:
                        select_size(driver, s["input"])
                    except:
                        pass

                # After (attempted) size select, resolve merchant id via JS state (unique per color+size)
                color_pid = get_current_color_product_id(color)  # e.g., '61002405'
                merchant_id = get_merchant_supplied_id_smart(driver, color["name"], s["size"], color_product_id=color_pid)
                
                # FINAL fallback to old DOM method if still empty (should rarely happen)
                if not merchant_id:
                    merchant_id = get_merchant_supplied_id(driver)

                # Name pieces
                variance = color["name"]
                size_variance = s["size"]
                variation_name = f"{variance} - {size_variance}"

                in_stock_rate = get_stock_state(s)

                # Get latest price blocks (some sites change price per size)
                _, price_now, sale_now = get_item_name_and_price(driver)
                price_val = price_now or price_text or ""
                sale_val = sale_now or ""

                row = Row(
                    item_name=item_name,
                    merchant_supplied_id=merchant_id,
                    variant_id=variant_id,
                    variation_name=variation_name,
                    variance=variance,
                    size_variance=size_variance,
                    price=price_val.replace("\n", " ").strip(),
                    sale_price=sale_val.replace("\n", " ").strip(),
                    in_stock_rate=in_stock_rate,
                    photo_url=photo_url,
                    product_description=product_description
                )
                rows.append(row)

        # Write CSV
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "item_name","merchant_supplied_id","variant_id","variation_name","variance",
                "size_variance","price","sale_price","in_stock_rate","photo_url","product_description"
            ])
            writer.writeheader()
            for r in rows:
                writer.writerow(asdict(r))

        print(f"Done. Rows: {len(rows)} → {OUTPUT_CSV}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
