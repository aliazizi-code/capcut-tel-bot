import os
import time
import base64
import cv2
import numpy as np
import shutil
from pathlib import Path
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from split_mp3 import get_split_mp3


load_dotenv()


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("success")

# ---------------- Browser Initialization ----------------
async def init_browser(context: ContextTypes.DEFAULT_TYPE):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    download_dir = os.path.join(base_dir, "download")
    os.makedirs(download_dir, exist_ok=True)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.popups": 0,
        "profile.managed_default_content_settings.images": 2  # ⛔️ جلوگیری از لود تصاویر
    })

    chrome_options.add_argument("--headless=new")  # ✅ حالت بدون UI (headless)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)
    context.application.bot_data["driver"] = driver
    return driver

# ---------------- /start Handler ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # دسترسی
    list_id = list(map(int, os.getenv("LIST_ID").split(',')))
    if update.effective_user.id not in list_id:
        return await update.message.reply_text("⛔️ دسترسی ندارید.")

    await update.message.reply_text("در حال بررسی وضعیت...")

    # 1) مرورگر را reuse کن یا بساز
    bot_data = context.application.bot_data
    if "driver" in bot_data:
        driver = bot_data["driver"]
        try:
            _ = driver.title
            await update.message.reply_text("✅ مرورگر قبلاً باز شده و فعاله.")
        except Exception:
            await update.message.reply_text("🔄 مرورگر قبلی بسته شده. راه‌اندازی مجدد...")
            driver = await init_browser(context)
    else:
        driver = await init_browser(context)

    wait = WebDriverWait(driver, timeout=30)
    driver.get(os.getenv("LOGIN_URL"))

    # 2) بررسی لاگین بودن
    if not driver.find_elements(By.NAME, "signUsername"):
        return await update.message.reply_text("✅ قبلاً لاگین شده‌اید.")

    # 3) لاگین
    await update.message.reply_text("🔐 لاگین نیستید — در حال لاگین...")
    try:
        btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//span[text()='Continue with CapCut Mobile']")))
        btn.click()
        await update.message.reply_text("✅ روی دکمه لاگین کلیک شد.")

        # پاپ‌آپ QR
        time.sleep(2)
        main_win = driver.current_window_handle
        popups = [w for w in driver.window_handles if w != main_win]
        if not popups:
            return await update.message.reply_text("❌ پنجره QR باز نشد.")
        driver.switch_to.window(popups[0])

        # canvas → تصویر
        canvas = wait.until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))
        data_b64 = driver.execute_script(
            "return arguments[0].toDataURL('image/png').split(',')[1];", canvas
        )
        img_data = base64.b64decode(data_b64)
        arr = np.frombuffer(img_data, np.uint8)
        img_np = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        # encode to PNG for telegram
        ok, buf = cv2.imencode(".png", img_np)
        if not ok:
            return await update.message.reply_text("❌ تبدیل تصویر به بایت‌ شکست خورد.")
        bio = BytesIO(buf.tobytes())
        bio.name = "qr.png"
        bio.seek(0)
        await update.message.reply_photo(photo=bio)

        # صبر برای بسته‌شدن پاپ‌آپ
        while len(driver.window_handles) > 1:
            time.sleep(1)
        driver.switch_to.window(main_win)
        await update.message.reply_text("✅ بازگشت به پنجره اصلی")

    except Exception as e:
        return await update.message.reply_text(f"⚠️ خطا در لاگین: {e}")

    # 4) Accept all
    try:
        time.sleep(5)
        accepts = driver.find_elements(By.XPATH, "//span[text()='Accept all']/ancestor::button")
        if accepts:
            accepts[0].click()
            await update.message.reply_text("✅ 'Accept all' کلیک شد")
    except Exception as e:
        await update.message.reply_text(f"⚠️ خطا در Accept all: {e}")

    await update.message.reply_text(" و منتظر ارسال فایل صوتی هستم.  🎉 مرورگر باز مانده است.")

# ---------------- Mp3 Upload Handler ----------------


async def handle_mp3_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    driver = context.application.bot_data.get("driver")
    if not driver:
        return await update.message.reply_text("❌ مرورگر راه‌اندازی نشده؛ ابتدا /start بزنید.")

    audio = update.message.audio
    if not audio or audio.mime_type != "audio/mpeg":
        return await update.message.reply_text("❌ فقط فایل‌های MP3 پشتیبانی می‌شوند.")

    character_name = (update.message.caption or "").strip()
    if not character_name:
        return await update.message.reply_text("❌ لطفاً نام کرکتر را در کپشن فایل MP3 بنویسید (مثلاً: Pam).")

    # ذخیره در پوشه input
    base_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    input_dir = base_dir / "input"
    input_dir.mkdir(exist_ok=True)
    file_name = audio.file_name or "input.mp3"
    input_path = input_dir / file_name

    await update.message.reply_text("📥 در حال ذخیره فایل در پوشه input…")
    tg_file = await audio.get_file()
    await tg_file.download_to_drive(str(input_path))

    # پردازش فایل
    await update.message.reply_text("🎛 در حال پردازش فایل و تقسیم به بخش‌ها…")
    splits_dir = base_dir / "splits"
    get_split_mp3(str(input_path), output_base_dir=splits_dir)

    download_dir = base_dir / "download"
    download_dir.mkdir(exist_ok=True)


    driver.refresh()
    WebDriverWait(driver, 30).until(lambda d: d.execute_script("return document.readyState") == "complete")
    await update.message.reply_text("🔄 مرورگر رفرش شد.")
    wait = WebDriverWait(driver, 30)


    # آپلود همه فایل‌ها
    split_files = sorted(splits_dir.glob("*.mp3"), key=lambda f: int(f.stem))
    if not split_files:
        return await update.message.reply_text("⚠️ هیچ فایل MP3 در پوشه splits پیدا نشد.")

    for file in split_files:
        try:
            driver.refresh()
            WebDriverWait(driver, 30).until(lambda d: d.execute_script("return document.readyState") == "complete")
            await update.message.reply_text("🔄 مرورگر رفرش شد.")
            wait = WebDriverWait(driver, 30)
            
            item_xpath = (
                f"//div[contains(@class,'toneItem-zsczqb')]"
                f"[.//div[contains(@class,'toneItem__name') and normalize-space(text())='{character_name}']]"
            )
            item = wait.until(EC.element_to_be_clickable((By.XPATH, item_xpath)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
            driver.execute_script("arguments[0].click();", item)
            driver.execute_script("arguments[0].classList.add('toneItem--selected-ZwhzHN');", item)
            await update.message.reply_text(f"🎭 کرکتر «{character_name}» انتخاب شد.")
            
            await update.message.reply_text(f"📤 آپلود فایل: {file.name}")
            file_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
            driver.execute_script(
                "arguments[0].style.display='block'; arguments[0].style.visibility='visible';", file_input
            )
            file_input.send_keys(str(file.resolve()))

            generate_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[span/text()='Generate']")))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", generate_btn)
            driver.execute_script("arguments[0].click();", generate_btn)
            await update.message.reply_text("▶️ دکمه Generate کلیک شد.")

            # کلیک روی Download > Audio only
            download_btn = wait.until(EC.element_to_be_clickable((
                By.XPATH, "//div[contains(@class,'download-button') and .//span[text()='Download']]"
            )))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", download_btn)
            driver.execute_script("arguments[0].click();", download_btn)

            dropdown_item = wait.until(EC.element_to_be_clickable((
                By.XPATH, "//div[@role='menuitem' and contains(text(),'Audio only')]"
            )))
            dropdown_item.click()

            # صبر برای ذخیره فایل
            await update.message.reply_text("⬇️ در حال دانلود فایل خروجی…")
            timeout = 60
            start = time.time()
            downloaded_file = None
            while time.time() - start < timeout:
                files = list(download_dir.glob("*.mp3"))
                files = [
                    f for f in files
                    if not f.name.endswith(".crdownload") and os.access(f, os.R_OK)
                ]
                if files:
                    newest = max(files, key=lambda f: f.stat().st_mtime)
                    if time.time() - newest.stat().st_mtime > 1:
                        downloaded_file = newest
                        break
                time.sleep(1)

            if downloaded_file:
                await update.message.reply_text(f"✅ فایل دانلود شد: {downloaded_file.name}")
            else:
                # await update.message.reply_text("⚠️ فایل خروجی دریافت نشد.")
                pass
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در فایل {file.name}: {e}")
            
    driver.refresh()
    WebDriverWait(driver, 30).until(lambda d: d.execute_script("return document.readyState") == "complete")
    await update.message.reply_text("🔄 مرورگر رفرش شد.")
    wait = WebDriverWait(driver, 30)

    await update.message.reply_text("🎉 تمام فایل‌ها پردازش، آپلود و دانلود شدند.")

# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))
    app.add_handler(MessageHandler(filters.AUDIO & ~filters.COMMAND, handle_mp3_audio))
    app.run_polling()

if __name__ == "__main__":
    main()