import datetime
import os
import re
import time
from subprocess import Popen

import log
import settings
from common import threaded
from pymediainfo import MediaInfo
from subtitles import get_subtitle_language


def _recursive_filepaths(dir_name):
    """
    Return a list of all files in the directory and its subdirectories.
    """
    list_of_file = os.listdir(dir_name)
    all_files = list()
    for entry in list_of_file:
        full_path = os.path.join(dir_name, entry)
        if os.path.isdir(full_path):
            all_files = all_files + _recursive_filepaths(full_path)
        else:
            all_files.append(full_path)
    return all_files


def _extract_subtitles_as_vtt(filepath):
    """
    Extracts subtitles from a video file and saves them as WebVTT files.
    :param str filepath: Path to the video file.
    """
    output_dir = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    filename_without_extension = os.path.splitext(basename)[0]
    media_info = MediaInfo.parse(filepath)
    sub_tracks = [
        (int(t.streamorder), t.language or "unknown")
        for (i, t) in enumerate(
            [t for t in media_info.tracks if t.track_type == "Text"]
        )
        if t.streamorder
    ]
    return Popen(
        f'ffmpeg -nostdin -v quiet -i "{filepath}" '
        + " ".join(
            [
                f'-map 0:{i} "{output_dir}/{filename_without_extension}.{i}_{lang}.vtt"'
                for (i, lang) in sub_tracks
            ]
        ),
        shell=True,
    )


def _convert_file_to_mp4(input_filepath, output_filepath, subtitle_filepaths=[]):
    output_extension = os.path.splitext(output_filepath)[1]
    media_info = MediaInfo.parse(input_filepath)
    audio_codecs = [
        t.format.lower() for t in media_info.tracks if t.track_type == "Audio"
    ]
    video_codecs = [
        t.format.lower() for t in media_info.tracks if t.track_type == "Video"
    ]
    needs_audio_conversion = not any("aac" in c for c in audio_codecs)
    needs_video_conversion = settings.CONVERT_VIDEO and not any("avc" in c for c in video_codecs)
    n_sub_tracks = len([t for t in media_info.tracks if t.track_type == "Text"])
    if media_info.tracks:
        try:
            duration = next(t.duration for t in media_info.tracks if t.duration)
            duration = int(round(duration / 1000))
        except StopIteration:
            duration = None
        with open(f"{output_filepath}{settings.LOG_POSTFIX}", "w") as f:
            f.write(f"{duration}\r")
    return Popen(
        " ".join(
            [
                "ffmpeg -nostdin",
                f'-i "{input_filepath}"',
                " ".join([f'-f srt -i "{fn}"' for (lang, fn) in subtitle_filepaths]),
                "-map 0:v?",
                "-map 0:a?",
                "-map 0:s?" if n_sub_tracks > 0 else "",
                f"-acodec aac -ab {settings.AAC_BITRATE} -ac {settings.AAC_CHANNELS}"
                if needs_audio_conversion
                else "-acodec copy",
                "-vcodec " + settings.VIDEO_CONVERSION_PARAMS
                if needs_video_conversion
                else "-vcodec copy",
                " ".join([f"-map {i}?" for i in range(1, len(subtitle_filepaths) + 1)]),
                " ".join(
                    [
                        f"-metadata:s:s:{i + n_sub_tracks} language='{subtitle_filepaths[i][0]}'"
                        for i in range(0, len(subtitle_filepaths))
                        if subtitle_filepaths[i][0] is not None
                    ]
                ),
                "-c:s mov_text",
                "-movflags faststart",
                "-v quiet -stats",
                f'"{output_filepath}{settings.INCOMPLETE_POSTFIX}{output_extension}" 2>> "{output_filepath}{settings.LOG_POSTFIX}"',
                "&&",
                f'mv "{output_filepath}{settings.INCOMPLETE_POSTFIX}{output_extension}" "{output_filepath}"',
            ]
        ),
        shell=True,
    )


def get_conversion_progress(filepath):
    """
    Get the conversion progress for a file.

    :param str filepath: The path to
    the file that is being converted.
    :returns float progress_percentage: The
    percentage of completion of the conversion process, as a float between 0
    and 1. If no log exists for this file, returns 0.0 (i.e., not started). If
    there are no lines in the log, returns 1 (i.e., finished). Otherwise
    calculates it based on how many seconds have elapsed since start time and
    total duration from first line in logfile divided by each other
    respectively.
    """
    log_filepath = f"{filepath}{settings.LOG_POSTFIX}"
    if os.path.isfile(log_filepath):
        with open(log_filepath, "r") as f:
            lines = f.readlines()
            first_line = lines[0]
            last_line = lines[-1]
            duration = int(first_line)
            current_duration = re.search(r"time=\s*(\d\d\:\d\d\:\d\d)\s*", last_line)
            if current_duration:
                current_duration = current_duration.group(1)
                current_duration = time.strptime(
                    current_duration.split(",")[0], "%H:%M:%S"
                )
                current_duration = datetime.timedelta(
                    hours=current_duration.tm_hour,
                    minutes=current_duration.tm_min,
                    seconds=current_duration.tm_sec,
                ).total_seconds()
                return current_duration / duration
    return 0.0


class VideoConverter:
    file_conversions = {}

    @threaded
    @log.catch_and_log_exceptions
    def convert_file(self, input_filepath, output_filepath):
        """
        Converts the given input file to an MP4 with subtitles in the given output
        file.

        :param input_filepath: The path of the video file to convert.
        :type
        input_filepath: str
        :param output_filepath: The path of the converted video
        file. If this already exists, it will be overwritten without warning. If it
        does not exist, it will be created as a result of this function call (but
        not necessarily immediately). It is recommended that you use
        :func`os.makedirs` before calling this function if you want to ensure that
        all necessary parent directories are created at once so that no errors
        occur during conversion due to missing directories later on down the line
        (e.g., when trying to extract subtitles from a newly-created MP4).  This
        parameter must end in ".mp4".
        """
        try:

            if len(self.file_conversions.keys()) >= settings.MAX_PARALLEL_CONVERSIONS:
                return
            if self.file_conversions.get(output_filepath):
                return

            self.file_conversions[output_filepath] = True

            output_dir = os.path.dirname(output_filepath)
            os.makedirs(output_dir, exist_ok=True)

            # Gather subtitle files
            basename = os.path.basename(input_filepath)
            filename_without_extension = os.path.splitext(basename)[0]

            subtitle_filepaths = [
                (get_subtitle_language(os.path.basename(filepath)), filepath)
                for filepath in _recursive_filepaths(os.path.dirname(input_filepath))
                if (os.path.basename(filepath).lower()).startswith(
                    filename_without_extension.lower()
                )
                and filepath.endswith(".srt")
            ]

            conversion = _convert_file_to_mp4(
                input_filepath, output_filepath, subtitle_filepaths=subtitle_filepaths
            )
            conversion.wait()

            if conversion.returncode != 0:
                raise Exception(f"Conversion failed for {input_filepath}")

            _extract_subtitles_as_vtt(output_filepath).wait()

        finally:
            try:
                del self.file_conversions[output_filepath]
            except KeyError:
                pass
