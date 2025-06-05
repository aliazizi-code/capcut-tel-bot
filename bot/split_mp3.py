import os
from pydub import AudioSegment
from clear_dir import clean_directory

def get_split_mp3(input_path, n_minutes=2, output_base_dir="splits"):
    clean_directory(output_base_dir)
    
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    os.makedirs(output_base_dir, exist_ok=True)
    
    # حذف ساخت پوشه شمارشی (counter)

    time_minutes = max(1, n_minutes - 1)
    max_duration_ms = time_minutes * 60 * 1000
    max_size_bytes = 49 * 1024 * 1024

    try:
        audio = AudioSegment.from_mp3(input_path)
    except Exception as e:
        raise RuntimeError(f"Error reading audio file: {str(e)}")

    total_duration_ms = len(audio)
    start_ms = 0
    part = 1
    output_files = []

    while start_ms < total_duration_ms:
        end_ms = min(start_ms + max_duration_ms, total_duration_ms)
        chunk = audio[start_ms:end_ms]

        temp_path = os.path.join(output_base_dir, f"temp_part_{part}.mp3")

        try:
            chunk.export(temp_path, format="mp3")
        except Exception as e:
            print(f"Temporary save error: {str(e)}")
            part += 1
            continue

        file_size = os.path.getsize(temp_path)
        adjustment_count = 0

        while file_size > max_size_bytes and (end_ms - start_ms) > 10000 and adjustment_count < 20:
            end_ms -= 10000
            chunk = audio[start_ms:end_ms]
            try:
                chunk.export(temp_path, format="mp3")
                file_size = os.path.getsize(temp_path)
            except:
                break
            adjustment_count += 1

        final_filename = f"{str(part).zfill(3)}.mp3"
        final_path = os.path.join(output_base_dir, final_filename)

        try:
            os.rename(temp_path, final_path)
            output_files.append(final_path)
        except OSError:
            try:
                chunk.export(final_path, format="mp3")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                output_files.append(final_path)
            except Exception as e:
                print(f"Final save error: {str(e)}")
                part += 1
                continue

        duration_minutes = round((end_ms - start_ms) / 60000, 2)
        size_mb = os.path.getsize(final_path) / (1024 * 1024)
        print(f"Saved: {final_path} (Duration: {duration_minutes} minutes, Size: {size_mb:.2f} MB)")

        start_ms = end_ms
        part += 1

    return output_files


