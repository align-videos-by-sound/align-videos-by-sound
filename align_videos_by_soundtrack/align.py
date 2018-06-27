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

_doc_template = '''
    %(prog)s <file1> <file2>

This program reports the offset difference for audio and video files,
containing audio recordings from the same event. It relies on ffmpeg being
installed and the python libraries scipy and numpy.

It reports back the offset. Example:

    %(prog)s good_video_shitty_audio.mp4 good_audio_shitty_video.mp4

    Result: The beginning of good_video_shitty_audio.mp4 needs to be trimmed off 11.348 seconds for all files to be in sync

'''
import os
import sys
from collections import defaultdict
import tempfile
import shutil
import logging

import numpy as np

from . import communicate

__all__ = [
    'SyncDetector',
    'main',
    ]

_logger = logging.getLogger(__name__)


if hasattr("", "decode"):  # python 2
    def _decode(s):
        return s.decode(sys.stdout.encoding)
else:
    def _decode(s):
        return s


def _make_horiz_bins(data, fft_bin_size, overlap, box_height):
    horiz_bins = defaultdict(list)

    # process sample and set matrix height
    for x, j in enumerate(range(int(-overlap), len(data), int(fft_bin_size - overlap))):
        sample_data = data[max(0, j):max(0, j) + fft_bin_size]
        if (len(sample_data) == fft_bin_size):  # if there are enough audio points left to create a full fft bin
            intensities = _fourier(sample_data)  # intensities is list of fft results
            for i in range(len(intensities)):
                box_y = i // box_height
                horiz_bins[box_y].append((intensities[i], x, i))  # (intensity, x, y)

    return horiz_bins


def _fourier(sample):  # , overlap):
    """
    Compute the one-dimensional discrete Fourier Transform

    INPUT: list with length of number of samples per second
    OUTPUT: list of real values len of num samples per second
    """
    fft_data = np.fft.fft(sample)  # Returns real and complex value pairs
    fft_data = fft_data[:len(fft_data) // 2]
    return list(np.sqrt(fft_data.real**2 + fft_data.imag**2))


def _make_vert_bins(horiz_bins, box_width):
    boxes = defaultdict(list)
    for key in list(horiz_bins.keys()):
        for i in range(len(horiz_bins[key])):
            box_x = horiz_bins[key][i][1] // box_width
            boxes[(box_x, key)].append((horiz_bins[key][i]))

    return boxes


def _find_bin_max(boxes, maxes_per_box):
    freqs_dict = defaultdict(list)
    for key in list(boxes.keys()):
        max_intensities = sorted(boxes[key], key=lambda x: -x[0])[:maxes_per_box]
        for j in range(len(max_intensities)):
            freqs_dict[max_intensities[j][2]].append(max_intensities[j][1])

    return freqs_dict


def _find_freq_pairs(freqs_dict_orig, freqs_dict_sample):
    for key in set(freqs_dict_sample.keys()) & set(freqs_dict_orig.keys()):
        for iitem in freqs_dict_sample[key]:  # determine time offset
            for jitem in freqs_dict_orig[key]:
                yield (iitem, jitem)


def _find_delay(time_pairs):
    t_diffs = defaultdict(int)
    for pair in time_pairs:
        delta_t = pair[0] - pair[1]
        t_diffs[delta_t] += 1
    t_diffs_sorted = sorted(list(t_diffs.items()), key=lambda x: x[1])
    # _logger.debug(t_diffs_sorted)
    time_delay = t_diffs_sorted[-1][0]

    return time_delay


class SyncDetector(object):
    def __init__(self, max_misalignment=0, sample_rate=48000, known_delay_ge_map={}):
        self._working_dir = tempfile.mkdtemp()
        self._max_misalignment = max_misalignment
        self._sample_rate = sample_rate
        self._known_delay_ge_map = known_delay_ge_map
        self._orig_infos = {}  # per filename

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        shutil.rmtree(self._working_dir)

    def _extract_audio(self, video_file, idx):
        """
        Extract audio from video file, save as wav auido file

        INPUT: Video file, and its index of input file list
        OUTPUT: Does not return any values, but saves audio as wav file
        """
        return communicate.media_to_mono_wave(
            video_file, self._working_dir,
            starttime_offset=self._known_delay_ge_map.get(idx, 0),
            duration=self._max_misalignment * 2,
            sample_rate=self._sample_rate)

    def _get_media_info(self, fn):
        if fn not in self._orig_infos:
            self._orig_infos[fn] = communicate.get_media_info(fn)
        return self._orig_infos[fn]

    def align(self, files, fft_bin_size=1024, overlap=0, box_height=512, box_width=43, samples_per_box=7):
        """
        Find time delays between video files
        """
        tmp_result = [0.0]

        # Process first file
        wavfile1 = self._extract_audio(files[0], 0)
        raw_audio1, rate = communicate.read_audio(wavfile1)
        bins_dict1 = _make_horiz_bins(
            raw_audio1,
            fft_bin_size, overlap, box_height)  # bins, overlap, box height
        del raw_audio1
        boxes1 = _make_vert_bins(bins_dict1, box_width)  # box width
        ft_dict1 = _find_bin_max(boxes1, samples_per_box)  # samples per box
        del boxes1

        for i in range(len(files) - 1):
            # Process second file
            wavfile2 = self._extract_audio(files[i + 1], i + 1)
            raw_audio2, rate = communicate.read_audio(wavfile2)
            bins_dict2 = _make_horiz_bins(
                raw_audio2,
                fft_bin_size, overlap, box_height)
            del raw_audio2
            boxes2 = _make_vert_bins(bins_dict2, box_width)
            ft_dict2 = _find_bin_max(boxes2, samples_per_box)
            del boxes2

            # Determie time delay
            pairs = _find_freq_pairs(ft_dict1, ft_dict2)
            delay = _find_delay(pairs)
            samples_per_sec = float(rate) / float(fft_bin_size)
            seconds = float(delay) / float(samples_per_sec)

            #
            tmp_result.append(-seconds)

        result = np.array(tmp_result)
        if self._known_delay_ge_map:
            for i in range(len(result)):
                if i in self._known_delay_ge_map:
                    result += self._known_delay_ge_map[i]
                    result[i] -= self._known_delay_ge_map[i]

        # build result
        pad_pre = result - result.min()
        trim_pre = -(pad_pre - pad_pre.max())
        orig_dur = np.array([
                self._get_media_info(fn)["duration"]
                for fn in files])
        pad_post = list(
            (pad_pre + orig_dur).max() - (pad_pre + orig_dur))
        trim_post = list(
            (orig_dur - trim_pre) - (orig_dur - trim_pre).min())
        #
        return [
            [
                files[i],
                {
                    "trim": trim_pre[i],
                    "pad": pad_pre[i],
                    "orig_duration": orig_dur[i],
                    "trim_post": trim_post[i],
                    "pad_post": pad_post[i],
                    }
                ]
            for i in range(len(files))]


def _bailout(parser):
    parser.print_usage()
    sys.exit(1)


def main(args=sys.argv):
    import argparse
    import json

    parser = argparse.ArgumentParser(prog=args[0], usage=_doc_template)
    parser.add_argument(
        '--max_misalignment',
        type=int, default=2*60,
        help='When handling media files with long playback time, \
it may take a huge amount of time and huge memory. \
In such a case, by changing this value to a small value, \
it is possible to indicate the scanning range of the media file to the program.')
    parser.add_argument(
        '--known_delay_ge_map',
        type=str,
        help='''When handling media files with long playback time, \
furthermore, when the delay time of a certain movie is large,
it may take a huge amount of time and huge memory. \
In such a case, you can give a mapping of the delay times that are roughly known. \
Please pass it in JSON format, like '{"1": 120}'. The key is an index corresponding \
to the file passed as "file_names". The value is the number of seconds, meaning \
"at least larger than this".''')
    parser.add_argument(
        '--sample_rate',
        type=int,
        default=48000,
        help='''In this program, delay is examined by unifying all the sample rates \
of media files into the same one. If this value is the value itself of the media file \
itself, the result will be more precise. However, this wastes a lot of memory, so you \
can reduce memory consumption by downsampling (instead losing accuracy a bit). \
The default value uses quite a lot of memory, but if it changes to a value of, for example, \
44100, 22050, etc., although a large error of about several tens of milliseconds \
increases, the processing time is greatly shortened.''')
    parser.add_argument(
        '--json',
        action="store_true",
        help='To report in json format.',)
    parser.add_argument(
        'file_names',
        nargs="*",
        help='Media files including audio streams. \
It is possible to pass any media that ffmpeg can handle.',)
    args = parser.parse_args(args[1:])
    known_delay_ge_map = {}
    if args.known_delay_ge_map:
        known_delay_ge_map = json.loads(args.known_delay_ge_map)
        known_delay_ge_map = {
            int(k): known_delay_ge_map[k]
            for k in known_delay_ge_map.keys()
            }

    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    if args.file_names and len(args.file_names) >= 2:
        file_specs = list(map(_decode, map(os.path.abspath, args.file_names)))
        # _logger.debug(file_specs)
    else:  # No pipe and no input file, print help text and exit
        _bailout(parser)
    non_existing_files = [path for path in file_specs if not os.path.isfile(path)]
    if non_existing_files:
        print("** The following are not existing files: %s **" % (','.join(non_existing_files),))
        _bailout(parser)

    with SyncDetector(
        max_misalignment=args.max_misalignment,
        sample_rate=args.sample_rate,
        known_delay_ge_map=known_delay_ge_map) as det:
        result = det.align(file_specs)
    if args.json:
        print(json.dumps({'edit_list': result}, indent=4))
    else:
        report = []
        for i, path in enumerate(file_specs):
            if not (result[i][1]["trim"] > 0):
                continue
            report.append(
                """Result: The beginning of '%s' needs to be trimmed off %.4f seconds \
(or to be added %.4f seconds padding) for all files to be in sync""" % (
                    path, result[i][1]["trim"], result[i][1]["pad"]))
        if report:
            print("\n".join(report))
        else:
            print("files are in sync already")


if __name__ == "__main__":
    main()
