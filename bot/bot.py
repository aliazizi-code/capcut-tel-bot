import os
import time
import base64
import cv2
import aiohttp
import asyncio
import aiofiles
import traceback
import numpy as np
from pathlib import Path
from io import BytesIO
from dotenv import load_dotenv
from telegram import Update
from telegram.helpers import escape_markdown
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.remote.webdriver import WebDriver as WD
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from split_mp3 import get_split_mp3
from merge_wave_converted_to_mp3 import merge_audio
from setup_dir import setup_directories

load_dotenv()

global_lock = asyncio.Lock()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! برای شروع، دستور /capcut را ارسال کنید.")

# ---------------- Browser Initialization ----------------
async def init_browser(context: ContextTypes.DEFAULT_TYPE):
    base_dir = Path(__file__).parent.resolve()
    download_dir = base_dir / "download"
    download_dir.mkdir(exist_ok=True)

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_experimental_option("prefs", {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1,
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.popups": 0,
        "profile.managed_default_content_settings.images": 2
    })

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)
    context.application.bot_data["driver"] = driver
    return driver

# ---------------- Refresh Browser ----------------
async def refresh_browser(driver: WD, update=None, timeout: int = 30):
    """رفرش مرورگر و انتظار تا لود کامل صفحه"""
    driver.refresh()
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    if update:
        await update.message.reply_text("🔄 مرورگر رفرش شد.")
    
    return WebDriverWait(driver, timeout)

# ---------------- /start Handler ----------------
async def capcut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    list_id = set(map(int, os.getenv("LIST_ID", "").split(',')))
    if user_id not in list_id:
        await update.message.reply_text("⛔️ شما دسترسی لازم را ندارید.")
        return

    driver = context.application.bot_data.get("driver")
    if driver:
        try:
            _ = driver.title
            await update.message.reply_text("✅ مرورگر قبلاً باز شده و فعاله.")
        except Exception:
            await update.message.reply_text("🔄 مرورگر قبلی بسته شده. راه‌اندازی مجدد...")
            driver = await init_browser(context)
    else:
        driver = await init_browser(context)

    wait = WebDriverWait(driver, 30)
    driver.get(os.getenv("LOGIN_URL"))

    try:
        sign_in_elements = driver.find_elements(By.NAME, "signUsername")
        if not sign_in_elements:
            await update.message.reply_text("✅ شما قبلاً لاگین کرده‌اید.")
            await update.message.reply_text("و منتظر ارسال فایل صوتی هستم. 🎉 مرورگر باز مانده است.")
            return
    except Exception as e:
        await update.message.reply_text(f"⚠️ خطا در بررسی وضعیت لاگین: {e}")
        return

    await update.message.reply_text("🔐 لاگین نیستید — در حال لاگین...")

    try:
        btn = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//span[text()='Continue with CapCut Mobile']")))
        btn.click()
        await update.message.reply_text("✅ روی دکمه لاگین کلیک شد.")

        time.sleep(2)
        main_win = driver.current_window_handle
        popups = [w for w in driver.window_handles if w != main_win]
        if not popups:
            await update.message.reply_text("❌ پنجره QR باز نشد.")
            return
        driver.switch_to.window(popups[0])

        canvas = wait.until(EC.presence_of_element_located((By.TAG_NAME, "canvas")))
        data_b64 = driver.execute_script(
            "return arguments[0].toDataURL('image/png').split(',')[1];", canvas
        )
        img_data = base64.b64decode(data_b64)
        arr = np.frombuffer(img_data, np.uint8)
        img_np = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        ok, buf = cv2.imencode(".png", img_np)
        if not ok:
            await update.message.reply_text("❌ تبدیل تصویر به بایت‌ شکست خورد.")
            return
        bio = BytesIO(buf.tobytes())
        bio.name = "qr.png"
        bio.seek(0)
        await update.message.reply_photo(photo=bio)

        while len(driver.window_handles) > 1:
            time.sleep(1)
        driver.switch_to.window(main_win)
        await update.message.reply_text("✅ بازگشت به پنجره اصلی")

    except Exception as e:
        await update.message.reply_text(f"⚠️ خطا در لاگین: {e}")
        return

    try:
        time.sleep(5)
        accepts = driver.find_elements(By.XPATH, "//span[text()='Accept all']/ancestor::button")
        if accepts:
            accepts[0].click()
            await update.message.reply_text("✅ 'Accept all' کلیک شد")
    except Exception as e:
        await update.message.reply_text(f"⚠️ خطا در Accept all: {e}")

    await update.message.reply_text("و منتظر ارسال فایل صوتی هستم. 🎉 مرورگر باز مانده است.")

# ---------------- Mp3 Upload Handler ----------------

async def handle_mp3_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if global_lock.locked():
        await update.message.reply_text("⚠️ عملیات دیگری در حال اجراست. لطفاً کمی صبر کنید.")
        return
    
    async with global_lock:
        try:
            
            
            # region Core


            # بررسی وضعیت درایور
            driver = context.application.bot_data.get("driver")
            if not driver:
                return await update.message.reply_text(
                    "❌ مرورگر راه‌اندازی نشده است.\n\nابتدا دستور /capcut را ارسال کنید."
                )

            # بررسی وجود فایل صوتی
            audio = update.message.audio
            if not audio:
                return await update.message.reply_text(
                    "❌ لطفاً یک فایل صوتی MP3 ارسال کنید."
                )

            # بررسی نوع فایل
            if audio.mime_type != "audio/mpeg":
                return await update.message.reply_text(
                    "❌ فقط فایل‌های MP3 با فرمت `audio/mpeg` پشتیبانی می‌شوند.",
                    parse_mode="Markdown",
                )

            # دریافت و بررسی نام کرکتر از کپشن
            character_name = (update.message.caption or "").strip()
            if not character_name:
                return await update.message.reply_text(
                    "❌ لطفاً نام کرکتر را در کپشن فایل MP3 بنویسید.\n\nمثال: *Pam*",
                    parse_mode="Markdown",
                )

            # 🔹 همه چیز اوکی است؛ ادامه‌ی پردازش در اینجا انجام می‌شود.
            await update.message.reply_text(
                f"✅ فایل MP3 با موفقیت دریافت شد.\n\n👤 کرکتر: *{escape_markdown(character_name)}*",
                parse_mode="Markdown",
            )

            # مسیرها
            folders = setup_directories()
            input_dir = folders["input"]
            splits_dir = folders["splits"]
            download_dir = folders["download"]
            merged_dir = folders["merged"]


            # دریافت مسیر فایل تلگرام
            file_name = audio.file_name or "input.mp3"
            input_path = input_dir / file_name

            # دریافت لینک مستقیم فایل
            tg_file = await audio.get_file()
            file_url = tg_file.file_path if tg_file.file_path.startswith("https") else f"https://api.telegram.org/file/bot{context.bot.token}/{tg_file.file_path}"

            # دانلود امن با استریم
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(file_url) as response:
                        if response.status != 200:
                            return await update.message.reply_text("❌ خطا در دریافت فایل از سرور تلگرام.")
                        
                        with open(input_path, "wb") as f:
                            async for chunk in response.content.iter_chunked(1024 * 1024):  # تکه‌های ۱ مگابایتی
                                f.write(chunk)
            except Exception as e:
                return await update.message.reply_text(f"❌ خطا در دانلود فایل: {str(e)}")

            
            # پردازش و تقسیم
            await update.message.reply_text("🎛 در حال پردازش فایل…")
            get_split_mp3(str(input_path), output_base_dir=splits_dir)

            # رفرش مرورگر
            await refresh_browser(driver, update)

            # پردازش فایل‌ها
            split_files = sorted(
                (f for f in splits_dir.glob("*.mp3") if f.stem.isdigit()),
                key=lambda f: int(f.stem)
            )

            if not split_files:
                return await update.message.reply_text("⚠️ هیچ فایل MP3 در پوشه splits پیدا نشد.")

            for file in split_files:
                try:
                    wait = await refresh_browser(driver, update)

                    # انتخاب کرکتر
                    item_xpath = (
                        f"//div[contains(@class,'toneItem-zsczqb')]"
                        f"[.//div[contains(@class,'toneItem__name') and normalize-space(text())='{character_name}']]"
                    )
                    item = wait.until(EC.element_to_be_clickable((By.XPATH, item_xpath)))
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                    driver.execute_script("arguments[0].click();", item)
                    driver.execute_script("arguments[0].classList.add('toneItem--selected-ZwhzHN');", item)
                    await update.message.reply_text(f"🎭 کرکتر «{character_name}» انتخاب شد.")

                    # آپلود
                    try:
                        
                        await update.message.reply_text(f"📤 درحال آپلود فایل: {file.name}")
                        file_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']")))
                        driver.execute_script(
                            "arguments[0].style.display='block'; arguments[0].style.visibility='visible';", file_input
                        )
                        file_input.send_keys(str(file.resolve()))
                        
                        
                    except WebDriverException as e:
                        print("Error:\n\n", e.msg)
                        print(traceback.format_exc())
                        
                    # کلیک Generate
                    generate_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[span/text()='Generate']")))
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", generate_btn)
                    driver.execute_script("arguments[0].click();", generate_btn)
                    await update.message.reply_text("▶️ دکمه Generate کلیک شد.")

                    # کلیک روی Download → Audio only
                    download_btn = wait.until(EC.element_to_be_clickable((
                        By.XPATH, "//div[contains(@class,'download-button') and .//span[text()='Download']]"
                    )))
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", download_btn)
                    driver.execute_script("arguments[0].click();", download_btn)
                    dropdown_item = wait.until(EC.element_to_be_clickable((
                        By.XPATH, "//div[@role='menuitem' and contains(text(),'Audio only')]"
                    )))
                    dropdown_item.click()
                    await update.message.reply_text("⬇️ در حال دانلود فایل خروجی…")

                    # انتظار تا فایل دانلود شود
                    timeout = 60 
                    poll_interval = 0.5
                    start_time = time.monotonic()
                    downloaded_file = None
                    # ذخیره لیست قبلی فایل‌ها و زمان آخرین تغییر آنها برای مقایسه
                    previous_files = {}

                    while (elapsed := time.monotonic() - start_time) < timeout:
                        current_files = {}
                        for f in download_dir.glob("*.mp3"):
                            if f.name.endswith(".crdownload") or not os.access(f, os.R_OK):
                                continue
                            try:
                                mtime = f.stat().st_mtime
                            except OSError:
                                continue
                            current_files[f] = mtime
                        
                        # اگر هیچ فایلی یافت نشد، ادامه می‌دهیم
                        if not current_files:
                            time.sleep(poll_interval)
                            continue

                        # پیدا کردن جدیدترین فایل
                        newest_file, newest_mtime = max(current_files.items(), key=lambda item: item[1])

                        # اگر فایل جدید است یا زمان تغییر آن نسبت به بار قبل بیشتر از 1 ثانیه گذشته باشد
                        prev_mtime = previous_files.get(newest_file)
                        if prev_mtime is None or (newest_mtime - prev_mtime) > 1:
                            # به روز رسانی زمان جدید
                            previous_files = current_files
                            time.sleep(poll_interval)
                            continue

                        # اگر 1 ثانیه از آخرین تغییر گذشته باشد یعنی فایل پایدار است
                        downloaded_file = newest_file
                        break
                        time.sleep(poll_interval)

                except Exception as e:
                    await update.message.reply_text(f"❌ خطا در فایل {file.name}: {e}")

            # مرج و ارسال
            async def merge_and_send(update, download_dir: Path, merged_dir: Path):
                try:
                    await update.message.reply_text("🔗 در حال ادغام فایل‌های خروجی…")
                    
                    loop = asyncio.get_running_loop()
                    # اجرای تابع blocking در thread جدا
                    await loop.run_in_executor(None, merge_audio, str(download_dir), str(merged_dir))

                    merged_files = [f for f in merged_dir.glob("*.mp3") if f.is_file() and os.access(f, os.R_OK)]

                    if not merged_files:
                        await update.message.reply_text("⚠️ هیچ فایل MP3 مرج‌شده‌ای در پوشه merged پیدا نشد.")
                        return
                    
                    final_file = max(merged_files, key=lambda f: f.stat().st_mtime)

                    # باز کردن فایل به صورت async و خواندن محتوا
                    async with aiofiles.open(final_file, "rb") as afp:
                        data = await afp.read()
                        await update.message.reply_audio(audio=data, caption="📦 فایل نهایی مرج‌شده")

                except Exception as e:
                    await update.message.reply_text(f"❌ خطا در ادغام یا ارسال فایل: {e}")
                else:
                    await update.message.reply_text("🎉 تمام فایل‌ها پردازش، دانلود و ارسال شدند.")
                    
            await merge_and_send(update, download_dir, merged_dir)
            
            # endregion
        
        
        except Exception as e:
            await update.message.reply_text(f"❌ خطایی رخ داد: {str(e)}")
        else:
            await update.message.reply_text("پایان..")
    



# ---------------- Shutdown browser ----------------
async def shutdown_browser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    driver = context.application.bot_data.get("driver")
    if not driver:
        return await update.message.reply_text("⚠️ هیچ مرورگری در حال اجرا نیست.")

    try:
        driver.quit()
        context.application.bot_data["driver"] = None  # پاک‌سازی دستی
        await update.message.reply_text("🛑 مرورگر با موفقیت بسته و خاموش شد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در بستن مرورگر: {e}")



# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()
    app.add_handler(CommandHandler("capcut", capcut))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO & ~filters.COMMAND, handle_mp3_audio))
    app.add_handler(CommandHandler("close", shutdown_browser))
    app.run_polling()

if __name__ == "__main__":
    main()