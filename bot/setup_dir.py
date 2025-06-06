from clear_dir import clean_directory
from pathlib import Path


def setup_directories():
    """
    تنظیم و پاک‌سازی مسیرهای مورد نیاز پروژه.
    """
    base_dir = Path(__file__).resolve().parent
    folders = {
        "input": base_dir / "input",
        "splits": base_dir / "splits",
        "download": base_dir / "download",
        "merged": base_dir / "merged",
    }

    # پاک‌سازی پوشه‌ها (در صورت وجود)
    for name, path in folders.items():
        clean_directory(path)
        path.mkdir(exist_ok=True, parents=True)

    return folders
