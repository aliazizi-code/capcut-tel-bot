import os
import shutil

def clean_directory(path: str, create_if_missing=False):
    if os.path.exists(path):
        if os.path.isdir(path):
            for filename in os.listdir(path):
                file_path = os.path.join(path, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)  # حذف فایل یا لینک
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)  # حذف پوشه
                except Exception as e:
                    print(f"خطا در حذف {file_path}: {e}")
        else:
            raise NotADirectoryError(f"مسیر داده‌شده یک پوشه نیست: {path}")
    else:
        if create_if_missing:
            os.makedirs(path)
            print(f"پوشه ساخته شد: {path}")
        else:
            print(f"پوشه وجود ندارد: {path}")
