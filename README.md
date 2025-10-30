# Hollister Variant Scraper

A fully automated product data extraction tool designed for dynamic, JavaScript-heavy eCommerce sites.  
This project focuses on scraping **Hollister** product pages that load content dynamically through React,  
handling 49 color–size combinations per item with precision.

---

## 🚀 Features

- Extracts **all color & size variations** (49 combinations per product)
- Captures key fields:
  - `item_name`
  - `merchant_supplied_id` *(unique per color + size)*
  - `variant_id` *(unique per color)*
  - `variation_name`
  - `variance` (color)
  - `size_variance` (size)
  - `price` / `sale_price`
  - `in_stock_rate`
  - `photo_url`
  - `product_description`
- Handles dynamic JS-rendered pages using **Selenium + undetected_chromedriver**
- Expands “Details & Material” section automatically to fetch variant IDs & descriptions
- Extracts unique merchant IDs from **window.Apollo cache & productPrices JSON**
- Clean CSV export for direct data analysis or integration

---

## 🧠 Tech Stack

| Component | Description |
|------------|-------------|
| **Python 3.10+** | Core language |
| **Selenium** | Browser automation for JS-heavy pages |
| **undetected_chromedriver** | Prevents site bot-detection |
| **Regex + JSON parsing** | Extracts IDs from internal JS objects |
| **CSV Writer** | Exports 49 structured rows per product |

---

## 🧩 How It Works

1. Opens a Hollister product page using **undetected Chrome**.
2. Iterates through all color swatches → for each color, clicks and expands **Details & Material**.
3. Fetches `variant_id` (unique per color).
4. For each size inside that color:
   - Selects size button
   - Extracts dynamic `merchant_supplied_id` from JS cache
   - Checks availability & pricing
5. Combines all data into one clean CSV file `variations.csv`.

---

## ⚙️ Setup & Run

### 1️⃣ Clone this repository
```bash
git clone https://github.com/<your-username>/hollister-variant-scraper.git
cd hollister-variant-scraper
