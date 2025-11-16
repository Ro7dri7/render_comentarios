# main.py
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from playwright.async_api import async_playwright
import pandas as pd
import os

app = FastAPI(title="Kayak Reviews Scraper API", version="1.0")

# Función auxiliar segura para extraer texto
async def safe_get_text(page, selector):
    try:
        elem = await page.query_selector(selector)
        return await elem.inner_text() if elem else ""
    except Exception:
        return ""

# Función para extraer reseñas de una página
async def extract_reviews_from_kayak_page(page, reviews_data, scraped_review_texts):
    reviews = await page.query_selector_all('div[data-testid="review"]')
    new_count = 0
    for review in reviews:
        try:
            author = await safe_get_text(review, 'span[data-testid="review-author"]')
            score = await safe_get_text(review, 'div[data-testid="review-score"]')
            text = await safe_get_text(review, 'div[data-testid="review-text"]')
            date = await safe_get_text(review, 'time')

            if not text or text in scraped_review_texts:
                continue

            scraped_review_texts.add(text)
            reviews_data.append({
                "Author": author,
                "Score": score,
                "Date": date,
                "Text": text
            })
            new_count += 1
        except Exception as e:
            print(f"⚠️ Error al extraer reseña: {e}")
    return new_count

# Función principal de scraping
async def scrape_kayak_reviews(url: str, filter_option: str, max_pages: int):
    reviews_data = []
    scraped_review_texts = set()

    async with async_playwright() as p:
        try:
            # ✅ Lanza Chromium clásico (evita headless_shell)
            browser = await p.chromium.launch(
                headless=True,
                channel="chrome",  # ← Fuerza el binario tradicional
                args=[
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-extensions',
                    '--disable-plugins',
                    '--disable-images',
                    '--disable-javascript',  # Opcional: mejora velocidad
                ]
            )

            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='es-ES'
            )
            page = await context.new_page()

            print(f"➡️ Navegando a: {url}")
            await page.goto(url, timeout=90000, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)

            # Verificar panel de reseñas
            try:
                await page.wait_for_selector('h2.Vdvb-title:has-text("Opiniones")', timeout=30000)
            except Exception as e:
                await browser.close()
                raise HTTPException(status_code=400, detail="No se encontró el panel de reseñas. Asegúrate de que la URL incluya '#navbar-item-reviews'.")

            # Extraer puntuación general (opcional)
            overall_score = await safe_get_text(page, 'div.hrp2-score')
            print(f"⭐ Puntuación general: {overall_score}")

            # Aplicar filtro de ordenamiento
            if filter_option != "recent":
                try:
                    filter_locator = page.locator(f'div[role="radio"]:has(input[value="{filter_option}"])')
                    if await filter_locator.is_visible():
                        await filter_locator.click()
                        await page.wait_for_timeout(5000)
                except Exception as e:
                    print(f"⚠️ No se pudo aplicar el filtro '{filter_option}': {e}")

            # Paginación
            current_page = 1
            while current_page <= max_pages:
                print(f"📄 Extrayendo página {current_page}...")
                await extract_reviews_from_kayak_page(page, reviews_data, scraped_review_texts)

                if current_page == max_pages:
                    break

                # Botón "Página siguiente" dentro de la sección de Opiniones
                next_btn = page.locator('[aria-label="Opiniones"] button[aria-label="Página siguiente"]')
                if await next_btn.count() == 0 or not await next_btn.is_enabled():
                    print("🏁 No hay más páginas.")
                    break

                await next_btn.click()
                await page.wait_for_timeout(5000)
                current_page += 1

            await browser.close()
            return reviews_data

        except Exception as e:
            if 'browser' in locals():
                await browser.close()
            raise e


# Endpoint principal (solo POST)
@app.post("/scrape")
async def scrape_endpoint(url: str, filter_option: str = "recent", max_pages: int = 1):
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="La URL debe comenzar con http:// o https://")
    if max_pages < 1 or max_pages > 10:
        raise HTTPException(status_code=400, detail="max_pages debe estar entre 1 y 10")

    try:
        data = await scrape_kayak_reviews(url, filter_option, max_pages)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

    if not data:
        raise HTTPException(status_code=404, detail="No se encontraron reseñas.")

    # Guardar CSV
    output_path = "/tmp/kayak_reviews.csv"  # Render: usa /tmp para archivos temporales
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')

    return FileResponse(output_path, media_type='text/csv', filename='kayak_reviews.csv')


# ✅ Ruta raíz amigable (opcional pero útil)
@app.get("/")
async def root():
    return {
        "mensaje": "✅ API de Kayak Scraper activa",
        "docs": "/docs",
        "uso": "Envía una petición POST a /scrape con url, filter_option y max_pages"
    }