#! /usr/bin/env python
# This script based on alignment_by_row_channels.py by Allison Deal, see
# https://github.com/allisonnicoledeal/VideoSync/blob/master/alignment_by_row_channels.py
DOC = '''
This program reports the offset difference for audio and video files,
containing audio recordings from the same event. It relies on ffmpeg being
installed and the python libraries scipy and numpy.


Usage:

    %s <file1> <file2>

It reports back the offset. Example:

    %s good_video_shitty_audio.mp4 good_audio_shitty_video.mp4

    Result: The beginning of good_video_shitty_audio.mp4 needs to be cropped 11.348 seconds for files to be in sync

''' % (__file__, __file__)
import os
import sys
from collections import defaultdict
import scipy.io.wavfile
import numpy as np
from subprocess import call
import tempfile
import shutil


# Read file
# INPUT: Audio file
# OUTPUT: Sets sample rate of wav file, Returns data read from wav file (numpy array of integers)
def read_audio(audio_file):
    rate, data = scipy.io.wavfile.read(audio_file)  # Return the sample rate (in samples/sec) and data from a WAV file
    return data, rate


def make_horiz_bins(data, fft_bin_size, overlap, box_height):
    horiz_bins = defaultdict(list)
    # process first sample and set matrix height
    sample_data = data[0:fft_bin_size]  # get data for first sample
    if (len(sample_data) == fft_bin_size):  # if there are enough audio points left to create a full fft bin
        intensities = fourier(sample_data)  # intensities is list of fft results
        for i in range(len(intensities)):
            box_y = i // box_height
            horiz_bins[box_y].append((intensities[i], 0, i))  # (intensity, x, y)

    # process remainder of samples
    x_coord_counter = 1  # starting at second sample, with x index 1
    for j in range(int(fft_bin_size - overlap), len(data), int(fft_bin_size - overlap)):
        sample_data = data[j:j + fft_bin_size]
        if (len(sample_data) == fft_bin_size):
            intensities = fourier(sample_data)
            for k in range(len(intensities)):
                box_y = k // box_height
                horiz_bins[box_y].append((intensities[k], x_coord_counter, k))  # (intensity, x, y)
        x_coord_counter += 1

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
        max_intensities = [(1, 2, 3)]
        for i in range(len(boxes[key])):
            if boxes[key][i][0] > min(max_intensities)[0]:
                if len(max_intensities) < maxes_per_box:  # add if < number of points per box
                    max_intensities.append(boxes[key][i])
                else:  # else add new number and remove min
                    max_intensities.append(boxes[key][i])
                    max_intensities.remove(min(max_intensities))
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
    # print(t_diffs_sorted)
    time_delay = t_diffs_sorted[-1][0]

    return time_delay


class SyncDetector(object):
    def __init__(self, max_misalignment=0):
        self._working_dir = tempfile.mkdtemp()
        if max_misalignment and max_misalignment > 0:
            self._ffmpeg_t_args = ("-t", "%d" % max_misalignment)
        else:
            self._ffmpeg_t_args = (None, None)

    def __enter__(self):
        return self

    def __exit__(self, type, value, tb):
        shutil.rmtree(self._working_dir)

    # Extract audio from video file, save as wav auido file
    # INPUT: Video file
    # OUTPUT: Does not return any values, but saves audio as wav file
    def extract_audio(self, video_file):
        track_name = os.path.basename(video_file)
        audio_output = track_name + "WAV.wav"  # !! CHECK TO SEE IF FILE IS IN UPLOADS DIRECTORY
        output = os.path.join(self._working_dir, audio_output)
        if not os.path.exists(output):
            call(filter(None, [
                    "ffmpeg", "-y",
                    self._ffmpeg_t_args[0], self._ffmpeg_t_args[1],
                    "-i", "%s" % video_file,
                    "-vn",
                    "-ac", "1",
                    "-f", "wav",
                    "%s" % output
                    ]), stderr=open(os.devnull, 'w'))
        return output

    # Find time delay between two video files
    def align(self, files, fft_bin_size=1024, overlap=0, box_height=512, box_width=43, samples_per_box=7):
        tmp_result = [0.0]

        # Process first file
        wavfile1 = self.extract_audio(files[0])
        raw_audio1, rate = read_audio(wavfile1)
        bins_dict1 = make_horiz_bins(raw_audio1[:44100 * 120], fft_bin_size, overlap, box_height)  # bins, overlap, box height
        boxes1 = make_vert_bins(bins_dict1, box_width)  # box width
        ft_dict1 = find_bin_max(boxes1, samples_per_box)  # samples per box

        for i in range(len(files) - 1):
            # Process second file
            wavfile2 = self.extract_audio(files[i + 1])
            raw_audio2, rate = read_audio(wavfile2)
            bins_dict2 = make_horiz_bins(raw_audio2[:44100 * 60], fft_bin_size, overlap, box_height)
            boxes2 = make_vert_bins(bins_dict2, box_width)
            ft_dict2 = find_bin_max(boxes2, samples_per_box)

            # Determie time delay
            pairs = find_freq_pairs(ft_dict1, ft_dict2)
            delay = find_delay(pairs)
            samples_per_sec = float(rate) / float(fft_bin_size)
            seconds = float(delay) / float(samples_per_sec)

            #
            tmp_result.append(-seconds)

        result = np.array(tmp_result)
        result -= result.min()

        return list(result)


def bailout():
    print(DOC)
    sys.exit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=DOC)
    parser.add_argument('file_names', nargs="*")
    parser.add_argument('--max_misalignment', type=int)
    args = parser.parse_args()

    if args.file_names and len(args.file_names) >= 2:
        file_specs = list(map(os.path.abspath, args.file_names))
        # print(file_specs)
    else:  # No pipe and no input file, print help text and exit
        bailout()
    non_existing_files = []
    for path in file_specs:
        if not os.path.isfile(path):
            non_existing_files.append(path)
    if non_existing_files:
        print("** The following are not existing files: %s **" % (','.join(non_existing_files),))
        bailout()

    with SyncDetector(args.max_misalignment) as det:
        result = det.align(file_specs)

    report = []
    for i, path in enumerate(file_specs):
        if not (result[i] > 0):
            continue
        report.append("""Result: The beginning of '%s' needs to be cropped %.4f seconds for files to be in sync""" % (
                path, result[i]))
    if report:
        print("\n".join(report))
    else:
        print("files are in sync already")
