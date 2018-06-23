#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# This script based on alignment_by_row_channels.py by Allison Deal, see
# https://github.com/allisonnicoledeal/VideoSync/blob/master/alignment_by_row_channels.py
from __future__ import unicode_literals

DOC = '''
This program reports the offset difference for audio and video files,
containing audio recordings from the same event. It relies on ffmpeg being
installed and the python libraries scipy and numpy.


Usage:

    %s <file1> <file2>

It reports back the offset. Example:

    %s good_video_shitty_audio.mp4 good_audio_shitty_video.mp4

    Result: The beginning of good_video_shitty_audio.mp4 needs to be trimmed off 11.348 seconds for all files to be in sync

''' % (__file__, __file__)
import os
import sys
from collections import defaultdict
import subprocess
import tempfile
import shutil
import logging

import numpy as np
import scipy.io.wavfile


_logger = logging.getLogger(__name__)


if hasattr("", "decode"):  # python 2
    def _encode(s):
        return s.encode(sys.stdout.encoding)

    def _decode(s):
        return s.decode(sys.stdout.encoding)
else:
    def _encode(s):
        return s

    def _decode(s):
        return s


# Read file
# INPUT: Audio file
# OUTPUT: Sets sample rate of wav file, Returns data read from wav file (numpy array of integers)
def read_audio(audio_file):
    rate, data = scipy.io.wavfile.read(audio_file)  # Return the sample rate (in samples/sec) and data from a WAV file
    return data, rate


def make_horiz_bins(data, fft_bin_size, overlap, box_height):
    horiz_bins = defaultdict(list)

    # process sample and set matrix height
    for x, j in enumerate(range(int(-overlap), len(data), int(fft_bin_size - overlap))):
        sample_data = data[max(0, j):max(0, j) + fft_bin_size]
        if (len(sample_data) == fft_bin_size):  # if there are enough audio points left to create a full fft bin
            intensities = fourier(sample_data)  # intensities is list of fft results
            for i in range(len(intensities)):
                box_y = i // box_height
                horiz_bins[box_y].append((intensities[i], x, i))  # (intensity, x, y)

    return horiz_bins


# Compute the one-dimensional discrete Fourier Transform
# INPUT: list with length of number of samples per second
# OUTPUT: list of real values len of num samples per second
def fourier(sample):  # , overlap):
    fft_data = np.fft.fft(sample)  # Returns real and complex value pairs
    fft_data = fft_data[:len(fft_data) // 2]
    return list(np.sqrt(fft_data.real**2 + fft_data.imag**2))


def make_vert_bins(horiz_bins, box_width):
    boxes = defaultdict(list)
    for key in list(horiz_bins.keys()):
        for i in range(len(horiz_bins[key])):
            box_x = horiz_bins[key][i][1] // box_width
            boxes[(box_x, key)].append((horiz_bins[key][i]))

    return boxes


def find_bin_max(boxes, maxes_per_box):
    freqs_dict = defaultdict(list)
    for key in list(boxes.keys()):
        max_intensities = sorted(boxes[key], key=lambda x: -x[0])[:maxes_per_box]
        for j in range(len(max_intensities)):
            freqs_dict[max_intensities[j][2]].append(max_intensities[j][1])

    return freqs_dict


def find_freq_pairs(freqs_dict_orig, freqs_dict_sample):
    for key in set(freqs_dict_sample.keys()) & set(freqs_dict_orig.keys()):
        for iitem in freqs_dict_sample[key]:  # determine time offset
            for jitem in freqs_dict_orig[key]:
                yield (iitem, jitem)


def find_delay(time_pairs):
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
        if max_misalignment and max_misalignment > 0:
            self._ffmpeg_t_args = ("-t", "%d" % (max_misalignment * 2))
        else:
            self._ffmpeg_t_args = (None, None)
        self._sample_rate = sample_rate
        self._known_delay_ge_map = known_delay_ge_map

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        shutil.rmtree(self._working_dir)

    # Extract audio from video file, save as wav auido file
    # INPUT: Video file, and its index of input file list
    # OUTPUT: Does not return any values, but saves audio as wav file
    def extract_audio(self, video_file, idx):
        _ffmpeg_ss_args = (None, None)
        if idx in self._known_delay_ge_map:
            ss_h = self._known_delay_ge_map[idx] // 3600
            ss_m = self._known_delay_ge_map[idx] // 60
            ss_s = self._known_delay_ge_map[idx] % 60
            _ffmpeg_ss_args = (
                "-ss",
                "%02d:%02d:%02d.000" % (ss_h, ss_m, ss_s)
                )

        track_name = os.path.basename(video_file)
        audio_output = track_name + "WAV.wav"  # !! CHECK TO SEE IF FILE IS IN UPLOADS DIRECTORY
        output = os.path.join(self._working_dir, audio_output)
        if not os.path.exists(output):
            cmd = list(filter(None, [
                    "ffmpeg", "-y",
                    _ffmpeg_ss_args[0], _ffmpeg_ss_args[1],
                    self._ffmpeg_t_args[0], self._ffmpeg_t_args[1],
                    "-i", "%s" % video_file,
                    "-vn",
                    "-ar", "%d" % self._sample_rate,
                    "-ac", "1",
                    "-f", "wav",
                    "%s" % output
                    ]))
            #_logger.debug(cmd)
            subprocess.check_call(map(_encode, cmd), stderr=open(os.devnull, 'w'))
        return output

    # Find time delay between two video files
    def align(self, files, fft_bin_size=1024, overlap=0, box_height=512, box_width=43, samples_per_box=7):
        tmp_result = [0.0]

        # Process first file
        wavfile1 = self.extract_audio(files[0], 0)
        raw_audio1, rate = read_audio(wavfile1)
        bins_dict1 = make_horiz_bins(
            raw_audio1,
            fft_bin_size, overlap, box_height)  # bins, overlap, box height
        del raw_audio1
        boxes1 = make_vert_bins(bins_dict1, box_width)  # box width
        ft_dict1 = find_bin_max(boxes1, samples_per_box)  # samples per box
        del boxes1

        for i in range(len(files) - 1):
            # Process second file
            wavfile2 = self.extract_audio(files[i + 1], i + 1)
            raw_audio2, rate = read_audio(wavfile2)
            bins_dict2 = make_horiz_bins(
                raw_audio2,
                fft_bin_size, overlap, box_height)
            del raw_audio2
            boxes2 = make_vert_bins(bins_dict2, box_width)
            ft_dict2 = find_bin_max(boxes2, samples_per_box)
            del boxes2

            # Determie time delay
            pairs = find_freq_pairs(ft_dict1, ft_dict2)
            delay = find_delay(pairs)
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

        result -= result.min()

        return list(result)


def bailout():
    print(DOC)
    sys.exit()


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description=DOC)
    parser.add_argument('--max_misalignment', type=int, default=2*60)
    parser.add_argument('--known_delay_ge_map', type=str)
    parser.add_argument('--json', action="store_true",)
    parser.add_argument('file_names', nargs="*")
    args = parser.parse_args()
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
        bailout()
    non_existing_files = []
    for path in file_specs:
        if not os.path.isfile(path):
            non_existing_files.append(path)
    if non_existing_files:
        print("** The following are not existing files: %s **" % (','.join(non_existing_files),))
        bailout()

    with SyncDetector(args.max_misalignment, known_delay_ge_map=known_delay_ge_map) as det:
        result = det.align(file_specs)
        max_late = max(result)
    crop_amounts = [-(offset - max_late) for offset in result]
    if args.json:
        print(json.dumps({'edit_list':list(zip(file_specs, crop_amounts))}, indent=4))
    else:
        report = []
        for i, path in enumerate(file_specs):
            if not (crop_amounts[i] > 0):
                continue
            report.append("""Result: The beginning of '%s' needs to be trimmed off %.4f seconds for all files to be in sync""" % (
                    path, crop_amounts[i]))
        if report:
            print("\n".join(report))
        else:
            print("files are in sync already")
