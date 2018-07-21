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
from .utils import check_and_decode_filenames
from . import _cache
from . import cli_common
from .align_params import SyncDetectorSummarizerParams


__all__ = [
    'SyncDetectorSummarizerParams',
    'SyncDetector',
    'main',
    ]

_logger = logging.getLogger(__name__)


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
        j = secs * float(self._params.sample_rate)
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

    def summarize_audiotrack(self, media):
        _logger.info("for '%s' begin", os.path.basename(media))
        exaud_args = dict(video_file=media, duration=self._params.max_misalignment)
        # First, try getting from cache.
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

        # Not found in cache.
        _logger.info("extracting audio tracks for '%s' begin", os.path.basename(media))
        wavfile = self._extract_audio(**exaud_args)
        _logger.info("extracting audio tracks for '%s' end", os.path.basename(media))
        rate, ft_dict = self._summarize_wav(wavfile)
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
        if freqs_dict_orig == freqs_dict_sample:
            return 0.0
        #
        t_diffs = defaultdict(int)
        for key in keys:
            for x_i in freqs_dict_sample[key]:  # determine time offset
                for x_j in freqs_dict_orig[key]:
                    delta_t = x_i - x_j
                    mincond_ok = math.isnan(min_delay) or delta_t >= min_delay
                    maxcond_ok = math.isnan(max_delay) or delta_t <= max_delay
                    if mincond_ok and maxcond_ok:
                        t_diffs[delta_t] += 1
        try:
            return self._x_to_secs(
                sorted(list(t_diffs.items()), key=lambda x: -x[1])[0][0])
        except IndexError as e:
            raise Exception(
                """I could not find a match. \
Are the target medias sure to shoot the same event?""")


class SyncDetector(object):
    def __init__(self, params=SyncDetectorSummarizerParams(), clear_cache=False):
        self._working_dir = tempfile.mkdtemp()
        self._impl = _FreqTransSummarizer(
            self._working_dir, params)
        self._orig_infos = {}  # per filename
        if clear_cache:
            _cache.clean("_align")

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
            return self._impl.summarize_audiotrack(files[idx])
        #
        ftds = {i: _each(i) for i in range(len(files))}
        _result1, _result2 = {}, {}
        for kdm_key in known_delay_map.keys():
            kdm = known_delay_map[kdm_key]
            ft = os.path.abspath(kdm_key)
            fb = os.path.abspath(kdm["base"])
            it_all = [i for i, f in enumerate(files) if f == ft]
            ib_all = [i for i, f in enumerate(files) if f == fb]
            for it in it_all:
                for ib in ib_all:
                    _result1[(ib, it)] = -self._impl.find_delay(
                        ftds[ib], ftds[it],
                        kdm.get("min", float('nan')), kdm.get("max", float('nan')))
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
    parser = cli_common.AvstArgumentParser(description="""\
This program reports the offset difference for audio and video files,
containing audio recordings from the same event. It relies on ffmpeg being
installed and the python libraries scipy and numpy.
""")
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
    known_delay_map = args.known_delay_map

    cli_common.logger_config()

    file_specs = check_and_decode_filenames(
        args.file_names, min_num_files=2)
    if not file_specs:
        _bailout(parser)
    with SyncDetector(
        params=args.summarizer_params,
        clear_cache=args.clear_cache) as det:
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
