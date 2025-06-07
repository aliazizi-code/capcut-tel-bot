import time
import os
from pathlib import Path

def wait_for_download_complete(download_dir: Path, expected_exts=("mp3", "wav"), timeout=60, poll_interval=0.5):
    """
    منتظر می‌ماند تا یک فایل دانلود شود.
    اگر فایل پسوندش ".crdownload" باشد یعنی در حال دانلود است،
    وقتی پسوند به یکی از پسوندهای مورد انتظار تغییر کرد، یعنی دانلود کامل شده.
    """

    start_time = time.monotonic()
    previous_files = set()

    while (elapsed := time.monotonic() - start_time) < timeout:
        current_files = list(download_dir.glob("*"))
        
        # فایل‌هایی که در حال دانلود هستند (پسوند crdownload)
        downloading_files = [f for f in current_files if f.suffix == ".crdownload"]

        # فایل‌های دانلود شده کامل (پسوند از expected_exts)
        completed_files = [f for f in current_files if f.suffix.lstrip(".").lower() in expected_exts]

        # اگر فایلی که در حال دانلود هست نبود و فایل کامل شد (پسوند تغییر کرده)
        if not downloading_files and completed_files:
            # فرض می‌کنیم فقط یکی از فایل‌ها باید باشه، اگر بیشتر بود می‌توانید اینجا تغییر بدید
            return completed_files[0]

        time.sleep(poll_interval)

    raise TimeoutError(f"فایل دانلود نشده یا دانلود کامل نشده در مدت {timeout} ثانیه.")
