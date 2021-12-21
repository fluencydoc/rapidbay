import os
import time
from xmlrpc.client import ProtocolError

import log
import settings
from iso639 import languages
from pythonopensubtitles.opensubtitles import OpenSubtitles
from pythonopensubtitles.utils import File


def _chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i : i + n]


@log.catch_and_log_exceptions
def download_all_subtitles(filepath):
    """
    Downloads subtitles for the given filepath.

    :param str filepath: The path
    to the video file.
    """
    dirname = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    basename_without_ext = os.path.splitext(basename)[0]
    ost = OpenSubtitles()
    ost.login(settings.OPENSUBTITLES_USERNAME, settings.OPENSUBTITLES_PASSWORD)
    f = File(filepath)
    h = f.get_hash()
    language_ids = [
      languages.get(part1=lang).part2b for lang in settings.SUBTITLE_LANGUAGES
    ]
    results_from_hash = (
            [
            item for sublist in
            [ost.search_subtitles([{"sublanguageid": langid, "moviehash": h}]) or [] for langid in language_ids]
            for item in sublist
        ]
    )
    languages_in_results_from_hash = [
        lang_id for lang_id in [r.get("SubLanguageID") for r in results_from_hash]
    ]
    results_from_filename = (
            [
            item for sublist in
            [ost.search_subtitles([{"sublanguageid": langid, "query": basename_without_ext}]) or [] for langid in language_ids]
            for item in sublist
        ]
    )
    results_from_filename_but_not_from_hash = [
        r
        for r in results_from_filename
        if r.get("SubLanguageID")
        and r.get("SubLanguageID") not in languages_in_results_from_hash
    ]
    results = results_from_hash + results_from_filename_but_not_from_hash
    results = [
        r
        for r in results
        if r["ISO639"] in settings.SUBTITLE_LANGUAGES
    ]
    wait_before_next_chunk = False
    for chunk in _chunks(results, 10):
        sub_ids = {
            r["IDSubtitleFile"]: f'{basename_without_ext}.{r["ISO639"]}.srt'
            for r in chunk
        }

        def _download_subtitle_chunk(retries=5):
            nonlocal ost
            if not sub_ids:
                return
            try:
                ost.download_subtitles(
                    [_id for _id in sub_ids.keys()],
                    override_filenames=sub_ids,
                    output_directory=dirname,
                    extension="srt",
                )
            except ProtocolError as e:
                if retries == 0:
                    raise e
                time.sleep(10)
                ost = OpenSubtitles()
                ost.login(None, None)
                _download_subtitle_chunk(retries=retries - 1)

        if wait_before_next_chunk:
            time.sleep(10)
        _download_subtitle_chunk()
        wait_before_next_chunk = True


def get_subtitle_language(subtitle_filename):
    """
    Given a subtitle filename, return the language of that subtitle file.
    :param str subtitle_filename: The name of the subtitle file to get the
    language for. Must end with ".srt".
    :returns: The two-letter ISO 639-2 code
    for this language, or None if it could not be determined from its filename.
    """
    subtitle_filename = subtitle_filename.lower()
    assert subtitle_filename.endswith(".srt")
    filename_without_extension = os.path.splitext(subtitle_filename)[0]
    try:
        three_letter_iso = filename_without_extension[-3:]
        return languages.get(part2b=three_letter_iso).part2b
    except KeyError:
        try:
            two_letter_iso = filename_without_extension[-2:]
            if two_letter_iso == "pb":
                two_letter_iso = "pt"
            return languages.get(part1=two_letter_iso).part2b
        except KeyError:
            return None
