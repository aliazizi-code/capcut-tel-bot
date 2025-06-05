from pydub import AudioSegment
import os
import re
import glob
import shutil
import subprocess
from datetime import datetime

def merge_audio(input_dir="download", output_dir="merged"):
    try:
        audio_files = glob.glob(os.path.join(input_dir, "*.wav")) + glob.glob(os.path.join(input_dir, "*.mp3"))
        if not audio_files:
            print("❌ No audio files found in the folder")
            return None

        file_timestamps = []
        pattern = r"D(\d{8})_T(\d{6})\.(wav|mp3)$"
        print(f"🔍 Checking {len(audio_files)} audio files...")

        for file_path in audio_files:
            filename = os.path.basename(file_path)
            match = re.search(pattern, filename)
            if match:
                date_str = match.group(1)
                time_str = match.group(2)
                file_ext = match.group(3).lower()
                timestamp = f"{date_str}{time_str}"
                file_timestamps.append((timestamp, file_path, file_ext))

        if not file_timestamps:
            print("❌ No audio files with correct timestamp pattern found")
            return None

        file_timestamps.sort(key=lambda x: x[0])
        sorted_files = [item[1] for item in file_timestamps]
        file_extensions = [item[2] for item in file_timestamps]

        merged_audio = AudioSegment.empty()
        valid_files = 0
        print("\n📁 Starting to merge files:")

        for i, file_path in enumerate(sorted_files):
            try:
                if os.path.getsize(file_path) == 0:
                    print(f"⚠️ Ignored empty file: {os.path.basename(file_path)}")
                    continue

                if file_extensions[i] == "wav":
                    segment = AudioSegment.from_wav(file_path)
                else:
                    temp_wav = f"temp_{i}.wav"
                    command = f'ffmpeg -i "{file_path}" -ar 44100 -ac 2 "{temp_wav}"'
                    subprocess.run(command, shell=True, check=True, capture_output=True)
                    segment = AudioSegment.from_wav(temp_wav)
                    os.remove(temp_wav)

                segment = segment.set_frame_rate(44100).set_channels(2)
                duration_sec = len(segment) / 1000
                print(f"➕ Adding: {os.path.basename(file_path)} - Duration: {duration_sec:.1f} seconds")
                merged_audio += segment
                valid_files += 1
            except Exception as e:
                print(f"❌ Error processing {os.path.basename(file_path)}: {str(e)}")

        if valid_files == 0:
            print("❌ No valid audio files to merge")
            return None

        total_seconds = len(merged_audio) / 1000
        print(f"\n✅ Total merged duration: {int(total_seconds // 60)}m {total_seconds % 60:.1f}s")

        os.makedirs(output_dir, exist_ok=True)
        first_timestamp = file_timestamps[0][0]
        last_timestamp = file_timestamps[-1][0]
        output_filename = f"merged_{first_timestamp}_{last_timestamp}.mp3"
        output_path = os.path.join(output_dir, output_filename)

        merged_audio.export(output_path,
                            format="mp3",
                            bitrate="320k",
                            parameters=["-ar", "44100", "-ac", "2", "-q:a", "0"])

        # # حذف فایل‌های ورودی پس از ادغام
        # for f in audio_files:
        #     try:
        #         os.remove(f)
        #     except Exception as e:
        #         print(f"⚠️ Couldn't delete {f}: {e}")

        # print(f"\n🎉 Merged file created at: {output_path}")
        # return output_path

    except Exception as e:
        print(f"\n❌ Error during process: {e}")
        return None



merge_audio(input_dir="/home/aliazizi-code/Desktop/step 3")
