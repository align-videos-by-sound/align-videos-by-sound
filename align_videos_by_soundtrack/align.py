#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# This script based on alignment_by_row_channels.py by Allison Deal, see
# https://github.com/allisonnicoledeal/VideoSync/blob/master/alignment_by_row_channels.py
"""
This module contains the detector class for knowing the offset
difference for audio and video files, containing audio recordings
from the same event. It relies on ffmpeg being installed and
the python libraries scipy and numpy.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import os
import sys
from collections import defaultdict
import math
import json
import tempfile
import shutil
import logging

import numpy as np

from . import communicate
from .utils import (
    check_and_decode_filenames,
    json_loads,
    validate_dict_one_by_template)
from . import _cache


__all__ = [
    'SyncDetectorSummarizerParams',
    'SyncDetector',
    'main',
    ]

_logger = logging.getLogger(__name__)


class SyncDetectorSummarizerParams(object):
    """
    Parameter used by SyncDetector for summarizing audio track.
    It affects the behavior until find_delay return. Conversely,
    known_delay_map affecting interpretation of find_delay result is not
    included here.

    * max_misalignment:
        When handling media files with long playback time,
        it may take a huge amount of time and huge memory.
        In such a case, by changing this value to a small value,
        it is possible to indicate the scanning range of the media
        file to the program.

    * sample_rate:
        In this program, delay is examined by unifying all the sample
        rates of media files into the same one. If this value is the
        value itself of the media file itself, the result will be more
        precise. However, this wastes a lot of memory, so you can
        reduce memory consumption by downsampling (instead losing
        accuracy a bit). The default value uses quite a lot of memory,
        but if it changes to a value of, for example, 44100, 22050,
        etc., although a large error of about several tens of
        milliseconds  increases, the processing time is greatly
        shortened.

    * fft_bin_size, overlap:
        "fft_bin_size" is the number of audio samples passed to the FFT.
        If it is small, it means "fine" in the time domain viewpoint,
        whereas the larger it can be resolved into more kinds of
        frequencies. There is a possibility that it becomes difficult
        to be deceived as the frequency is examined finely, but instead
        the time step width of the delay detection becomes "coarse".
        "overlap" is in order to solve this dilemma. That is, windows
        for FFT are examined by overlapping each other. "overlap" must
        be less than "fft_bin_size".

    * box_height, box_width, maxes_per_box:
        This program sees the characteristics of the audio track by
        adopting a representative which has high strength in a small
        box divided into the time axis and the frequency axis.
        These parameters are those.

        Be careful as to how to give "box_height" is not easy to
        understand. It depends on the number of samples given to the
        FFT. That is, it depends on fft_bin_size - overlap. For
        frequencies not to separate, ie, not to create a small box,
        box_height should give (fft_bin_size - overlap) / 2.

    * afilter:
        This program begins by first extracting audio tracks from the
        media with ffmpeg. In this case, it is an audio filter given to
        ffmpeg. If the media is noisy, for example, it may be good to
        give a bandpass filter etc.

    * lowcut, highcut:
        It is a value for ignoring (truncating) the frequency of
        a specific range at the time of summarizing. This is more
        violent and foolish, unlike the so-called proper low cut high
        cut filter, but it is useful in some cases.

        The same attention as "box_height" holds. Again, the full
        range is (fft_bin_size - overlap) / 2.
    """
    def __init__(self, **kwargs):
        self.sample_rate = kwargs.get("sample_rate", 48000)

        self.fft_bin_size = kwargs.get("fft_bin_size", 1024)
        self.overlap = kwargs.get("overlap", 0)
        self.box_height = kwargs.get("box_height", self.fft_bin_size // 2)
        self.box_width = kwargs.get("box_width", 43)
        self.maxes_per_box = kwargs.get("maxes_per_box", 7)

        self.afilter = kwargs.get("afilter", "")

        max_misalignment = communicate.parse_time(
            kwargs.get("max_misalignment", 1800))
        if max_misalignment:
            # max_misalignment only cuts out the media. After cutting out,
            # we need to decide how much to investigate, If there really is
            # a delay close to max_misalignment indefinitely, for true delay
            # detection, it is necessary to cut out and investigate it with
            # a value slightly larger than max_misalignment. This can be
            # thought of as how many loops in _FreqTransSummarizer#summarize
            # should be minimized.
            #(fft_bin_size - overlap) / sample_rate
            max_misalignment += 512 * ((
                    self.fft_bin_size - self.overlap) / self.sample_rate)
            #_logger.debug(maxmisal)
        self.max_misalignment = max_misalignment

        self.lowcut = kwargs.get("lowcut")
        self.highcut = kwargs.get("highcut")

    @staticmethod
    def from_json(s):
        if s:
            d = json_loads(s)

            tmpl = SyncDetectorSummarizerParams()
            validate_dict_one_by_template(d, tmpl.__dict__)
            return SyncDetectorSummarizerParams(**d)
        return SyncDetectorSummarizerParams()


class _FreqTransSummarizer(object):
    def __init__(self, working_dir, params):
        self._working_dir = working_dir
        self._params = params

    def _summarize(self, data):
        """
        Return characteristic frequency transition's summary.
    
        The dictionaries to be returned are as follows:
        * key: The frequency appearing as a peak in any time zone.
        * value: A list of the times at which specific frequencies occurred.
        """
        freqs_dict = defaultdict(list)

        boxes = defaultdict(list)
        for x, j in enumerate(
            range(
                int(-self._params.overlap),
                len(data),
                int(self._params.fft_bin_size - self._params.overlap))):

            sample_data = data[max(0, j):max(0, j) + self._params.fft_bin_size]
            if (len(sample_data) == self._params.fft_bin_size):  # if there are enough audio points left to create a full fft bin
                intensities = np.abs(np.fft.fft(sample_data))  # intensities is list of fft results
                box_x = x // self._params.box_width
                for y in range(len(intensities) // 2):
                    box_y = y // self._params.box_height
                    # x: corresponding to time
                    # y: corresponding to freq
                    if self._params.lowcut is not None and \
                            isinstance(self._params.lowcut, (int,)):
                        if y <= self._params.lowcut:
                            continue
                    if self._params.highcut is not None and \
                            isinstance(self._params.highcut, (int,)):
                        if y >= self._params.highcut:
                            continue

                    boxes[(box_x, box_y)].append((intensities[y], x, y))
                    if len(boxes[(box_x, box_y)]) > self._params.maxes_per_box:
                        boxes[(box_x, box_y)].remove(min(boxes[(box_x, box_y)]))
        #
        for box_x, box_y in list(boxes.keys()):
            for intensity, x, y in boxes[(box_x, box_y)]:
                freqs_dict[y].append(x)

        del boxes
        return freqs_dict

    def _secs_to_x(self, secs):
        j = (secs if secs is not None else 0) * float(self._params.sample_rate)
        x = (j + self._params.overlap) / (self._params.fft_bin_size - self._params.overlap)
        return x

    def _x_to_secs(self, x):
        j = x * (self._params.fft_bin_size - self._params.overlap) - self._params.overlap
        return float(j) / self._params.sample_rate

    def _summarize_wav(self, wavfile):
        raw_audio, rate = communicate.read_audio(wavfile)
        result = self._summarize(raw_audio)
        del raw_audio
        return rate, result

    def _extract_audio(self, video_file, duration):
        """
        Extract audio from video file, save as wav auido file

        INPUT: Video file, and its index of input file list
        OUTPUT: Does not return any values, but saves audio as wav file
        """
        return communicate.media_to_mono_wave(
            video_file, self._working_dir,
            duration=duration,
            sample_rate=self._params.sample_rate,
            afilter=self._params.afilter)

    def summarize_audiotrack(self, media, dont_cache):
        _logger.info("for '%s' begin", os.path.basename(media))
        exaud_args = dict(video_file=media, duration=self._params.max_misalignment)
        # First, try getting from cache.
        ck = None
        if not dont_cache:
            for_cache = dict(exaud_args)
            for_cache.update(self._params.__dict__)
            for_cache.update(dict(
                    atime=os.path.getatime(media)
                    ))
            ck = _cache.make_cache_key(**for_cache)
            cv = _cache.get("_align", ck)
            if cv:
                _logger.info("for '%s' end", os.path.basename(media))
                return cv[1]
        else:
            _cache.clean("_align")

        # Not found in cache.
        _logger.info("extracting audio tracks for '%s' begin", os.path.basename(media))
        wavfile = self._extract_audio(**exaud_args)
        _logger.info("extracting audio tracks for '%s' end", os.path.basename(media))
        rate, ft_dict = self._summarize_wav(wavfile)
        if not dont_cache:
            _cache.set("_align", ck, (rate, ft_dict))
        _logger.info("for '%s' end", os.path.basename(media))
        return ft_dict

    def find_delay(
        self,
        freqs_dict_orig, freqs_dict_sample,
        min_delay=float('nan'),
        max_delay=float('nan')):
        #
        min_delay, max_delay = self._secs_to_x(min_delay), self._secs_to_x(max_delay)
        keys = set(freqs_dict_sample.keys()) & set(freqs_dict_orig.keys())
        #
        if not keys:
            raise Exception(
                """I could not find a match. Consider giving a large value to \
"max_misalignment" if the target medias are sure to shoot the same event.""")
        #
        t_diffs = defaultdict(int)
        for key in keys:
            for x_i in freqs_dict_sample[key]:  # determine time offset
                for x_j in freqs_dict_orig[key]:
                    delta_t = x_i - x_j
                    mincond_ok = math.isnan(min_delay) or delta_t >= min_delay
                    maxcond_ok = math.isnan(max_delay) or delta_t <= max_delay
                    inc = 1 if mincond_ok and maxcond_ok else 0
                    t_diffs[delta_t] += inc
    
        t_diffs_sorted = sorted(list(t_diffs.items()), key=lambda x: x[1])
        # _logger.debug(t_diffs_sorted)
        time_delay = t_diffs_sorted[-1][0]

        return self._x_to_secs(time_delay)


class SyncDetector(object):
    def __init__(self, params=SyncDetectorSummarizerParams(), dont_cache=False):
        self._working_dir = tempfile.mkdtemp()
        self._impl = _FreqTransSummarizer(
            self._working_dir, params)
        self._dont_cache = dont_cache
        self._orig_infos = {}  # per filename

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        retry = 3
        while retry > 0:
            try:
                shutil.rmtree(self._working_dir)
                break
            except:
                import time
                retry -= 1
                time.sleep(1)

    def _get_media_info(self, fn):
        if fn not in self._orig_infos:
            self._orig_infos[fn] = communicate.get_media_info(fn)
        return self._orig_infos[fn]

    def _align(self, files, known_delay_map):
        """
        Find time delays between video files
        """
        def _each(idx):
            return self._impl.summarize_audiotrack(
                files[idx], self._dont_cache)
        #
        ftds = {i: _each(i) for i in range(len(files))}
        _result1, _result2 = {}, {}
        for kdm_key in known_delay_map.keys():
            kdm = known_delay_map[kdm_key]
            try:
                it = files.index(os.path.abspath(kdm_key))
                ib = files.index(os.path.abspath(kdm["base"]))
            except ValueError:  # simply ignore
                continue
            _result1[(ib, it)] = -self._impl.find_delay(
                ftds[ib], ftds[it], kdm.get("min"), kdm.get("max"))
        #
        _result2[(0, 0)] = 0.0
        for i in range(len(files) - 1):
            if (0, i + 1) in _result1:
                _result2[(0, i + 1)] = _result1[(0, i + 1)]
            elif (i + 1, 0) in _result1:
                _result2[(0, i + 1)] = -_result1[(i + 1, 0)]
            else:
                _result2[(0, i + 1)] = -self._impl.find_delay(ftds[0], ftds[i + 1])
        #        [0, 1], [0, 2], [0, 3]
        # known: [1, 2]
        # _______________^^^^^^[0, 2] must be calculated by [0, 1], and [1, 2]
        # 
        # known: [1, 2], [2, 3]
        # _______________^^^^^^[0, 2] must be calculated by [0, 1], and [1, 2]
        # _______________^^^^^^^^[0, 3] must be calculated by [0, 2], and [2, 3]
        for ib, it in sorted(_result1.keys()):
            for i in range(len(files) - 1):
                if ib > 0 and it == i + 1 and (0, i + 1) not in _result1 and (i + 1, 0) not in _result1:
                    _result2[(0, it)] = _result2[(0, ib)] - _result1[(ib, it)]
                elif it > 0 and ib == i + 1 and (0, i + 1) not in _result1 and (i + 1, 0) not in _result1:
                    _result2[(0, ib)] = _result2[(0, it)] + _result1[(ib, it)]

        # build result
        result = np.array([_result2[k] for k in sorted(_result2.keys())])
        pad_pre = result - result.min()
        _logger.debug(
            list(zip(
                    map(os.path.basename, files),
                    ["%.3f" % pp for pp in pad_pre])))  #
        trim_pre = -(pad_pre - pad_pre.max())
        #
        return pad_pre, trim_pre

    def get_media_info(self, files):
        """
        Get information about the media (by calling ffprobe).

        Originally the "align" method had been internally acquired to get
        "pad_post" etc. When trying to implement editing processing of a
        real movie, it is very frequent to want to know these information
        (especially duration) in advance. Therefore we decided to release
        this as a method of this class. Since the retrieved result is held
        in the instance variable of class, there is no need to worry about
        performance.
        """
        return [self._get_media_info(fn) for fn in files]

    def align(
        self, files, known_delay_map={}):
        """
        Find time delays between video files
        """
        pad_pre, trim_pre = self._align(
            files, known_delay_map)
        #
        infos = self.get_media_info(files)
        orig_dur = np.array([inf["duration"] for inf in infos])
        strms_info = [
            (inf["streams"], inf["streams_summary"]) for inf in infos]
        pad_post = list(
            (pad_pre + orig_dur).max() - (pad_pre + orig_dur))
        trim_post = list(
            (orig_dur - trim_pre) - (orig_dur - trim_pre).min())
        #
        return [{
                "trim": trim_pre[i],
                "pad": pad_pre[i],
                "orig_duration": orig_dur[i],
                "trim_post": trim_post[i],
                "pad_post": pad_post[i],
                "orig_streams": strms_info[i][0],
                "orig_streams_summary": strms_info[i][1],
                }
                for i in range(len(files))]

    @staticmethod
    def summarize_stream_infos(result_from_align):
        """
        This is a service function that calculates several summaries on
        information about streams of all medias returned by
        SyncDetector#align.

        Even if "align" has only detectable delay information, you are
        often in trouble. This is because editing for lineup of targeted
        plural media involves unification of sampling rates (etc) in many
        cases.

        Therefore, this function calculates the maximum sampling rate etc.
        through all files, and returns it in a dictionary format.
        """
        result = dict(
            max_width=0,
            max_height=0,
            max_sample_rate=0,
            max_fps=0.0,
            has_video = [],
            has_audio = [])
        for ares in result_from_align:
            summary = ares["orig_streams_summary"]  # per single media

            result["max_width"] = max(
                result["max_width"], summary["max_resol_width"])
            result["max_height"] = max(
                result["max_height"], summary["max_resol_height"])
            result["max_sample_rate"] = max(
                result["max_sample_rate"], summary["max_sample_rate"])
            result["max_fps"] = max(
                result["max_fps"], summary["max_fps"])

            result["has_video"].append(
                summary["num_video_streams"] > 0)
            result["has_audio"].append(
                summary["num_audio_streams"] > 0)
        return result


def _bailout(parser):
    parser.print_help()
    sys.exit(1)


def main(args=sys.argv):
    import argparse, textwrap

    parser = argparse.ArgumentParser(description=textwrap.dedent("""\
This program reports the offset difference for audio and video files,
containing audio recordings from the same event. It relies on ffmpeg being
installed and the python libraries scipy and numpy.

Delay detection by feature comparison of frequency intensity may be wrong.
Since it is an approach that takes only one maximum value of the delay 
which can best explain the difference in the intensity distribution, if 
it happens to have a range where characteristics are similar, it adopts it 
by mistake.

As a last resort, you can make it misleading by giving "known_delay_map",
but it can be rarely solved by adjusting various parameters used by the program
for summarization. If you want to do this, pass it to the "-summarizer_params"
option in JSON format. The parameter description is as follows:

%s
""" % SyncDetectorSummarizerParams.__doc__), formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--summarizer_params',
        type=str,
        help="""See above explanation.""")
    parser.add_argument(
        '--known_delay_map',
        type=str,
        default="{}",
        help='''\
Delay detection by feature comparison of frequency intensity may be wrong.
Since it is an approach that takes only one maximum value of the delay 
which can best explain the difference in the intensity distribution, if 
it happens to have a range where characteristics are similar, it adopts it 
by mistake. "known_delay_map" is a mechanism for forcing this detection
error manually. For example, if the detection process returns 3 seconds
despite knowing that the delay is greater than at least 20 minutes,
you can complain with using "known_delay_map" like "It's over 20 minutes!".
Please pass it in JSON format, like 
'{"foo.mp4": {"min": 120, "max": 140, "base": "bar.mp4"}}'
Specify the adjustment as to which media is adjusted to "base", the minimum and 
maximum delay as "min", "max". The values of "min", "max"
are the number of seconds.''')
    parser.add_argument(
        '--dont_cache',
        action="store_true",
        help='''Normally, this script stores the result in cache ("%s"). \
If you hate this behaviour, specify this option.''' % (
            _cache.cache_root_dir))
    parser.add_argument(
        '--json',
        action="store_true",
        help='To report in json format.',)
    parser.add_argument(
        'file_names',
        nargs="+",
        help='Media files including audio streams. \
It is possible to pass any media that ffmpeg can handle.',)
    args = parser.parse_args(args[1:])
    known_delay_map = json.loads(args.known_delay_map)

    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stderr,
        format="%(created)f|%(levelname)5s:%(module)s#%(funcName)s:%(message)s")

    file_specs = check_and_decode_filenames(
        args.file_names, min_num_files=2)
    if not file_specs:
        _bailout(parser)
    params = SyncDetectorSummarizerParams.from_json(args.summarizer_params)
    with SyncDetector(
        params=params,
        dont_cache=args.dont_cache) as det:
        result = det.align(
            file_specs,
            known_delay_map=known_delay_map)
    if args.json:
        print(json.dumps(
                {'edit_list': list(zip(file_specs, result))}, indent=4, sort_keys=True))
    else:
        report = []
        for i, path in enumerate(file_specs):
            if not (result[i]["trim"] > 0):
                continue
            report.append(
                """Result: The beginning of '%s' needs to be trimmed off %.4f seconds \
(or to be added %.4f seconds padding) for all files to be in sync""" % (
                    path, result[i]["trim"], result[i]["pad"]))
        if report:
            print("\n".join(report))
        else:
            print("files are in sync already")


if __name__ == "__main__":
    main()
