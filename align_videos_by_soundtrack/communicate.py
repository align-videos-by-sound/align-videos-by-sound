# -*- coding: utf-8 -*-
#
"""
This module contains helpers for cooperation processing with
external programs (such as ffmpeg) on ​​which this library depends.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import subprocess
import sys
import os
import re
import logging

import scipy.io.wavfile

__all__ = [
    "check_call", "check_stderroutput",
    "read_audio",
    "get_media_info",
    "media_to_mono_wave",
    "duration_to_hhmmss",
    ]

_logger = logging.getLogger(__name__)


if hasattr("", "decode"):  # python 2
    def _encode(s):
        return s.encode(sys.stdout.encoding)
else:
    def _encode(s):
        return s


# ##################################
#
# low-level APIs
#

def _filter_args(*cmd):
    """
    do filtering None, and do encoding items to bytes
    (in Python 2).
    """
    return list(map(_encode, filter(None, *cmd)))

    
def check_call(*popenargs, **kwargs):
    """
    Basically do simply forward args to subprocess#check_call, but this
    does two things:

    * It does encoding these to bytes in Python 2.
    * It does omitting `None` in *cmd.
    
    """
    cmd = kwargs.get("args")
    if cmd is None:
        cmd = popenargs[0]
    subprocess.check_call(
        _filter_args(cmd), **kwargs)


def check_stderroutput(*popenargs, **kwargs):
    """
    Unfortunately, ffmpeg and ffprobe throw out the information
    we want into the standard error output, and subprocess.check_output
    discards the standard error output. This function is obtained by
    rewriting subprocess.check_output for standard error output.

    And this does two things:

    * It does encoding these to bytes in Python 2.
    * It does omitting `None` in *cmd.
    """
    if 'stderr' in kwargs:
        raise ValueError(
            'stderr argument not allowed, it will be overridden.')
    cmd = kwargs.get("args")
    if cmd is None:
        cmd = popenargs[0]
    #
    process = subprocess.Popen(
        _filter_args(cmd),
        stderr=subprocess.PIPE,
        **kwargs)
    stdout_output, stderr_output = process.communicate()
    retcode = process.poll()
    if retcode:
        raise subprocess.CalledProcessError(
            retcode, list(cmd), output=stderr_output)
    return stderr_output


# ##################################
#
# higher-level APIs
#
def read_audio(audio_file):
    """
    Read file

    INPUT: Audio file
    OUTPUT: Sets sample rate of wav file, Returns data read from wav file (numpy array of integers)
    """
    # Return the sample rate (in samples/sec) and data from a WAV file

    # By using mmap you can reduce memory usage. I do not know whether this is good from
    # the viewpoint of processing speed. However, when dealing with a realistic movie that
    # this package deals with, the most problematic is the memory used. For example, If
    # a poor PC with only 4 GB of physical memory handles a movie of about "VERY SHORT" 20
    # minutes, it will cause you to fall into a state where you can not do any work.
    rate, data = scipy.io.wavfile.read(
        audio_file,
        mmap=True)
    return data, rate


def _parse_ffprobe_output(inputstr):
    r"""
    >>> import json
    >>> s = '''Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'input.mp4':
    ...  Metadata:
    ...    major_brand     : isom
    ...    minor_version   : 512
    ...    compatible_brands: isomiso2avc1mp41
    ...    encoder         : Lavf56.40.101
    ...  Duration: 00:24:59.55, start: 0.000000, bitrate: 4457 kb/s
    ...    Stream #0:0(und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, bt709), 1920x1080 [SAR 1:1 DAR 16:9], 4324 kb/s, 29.97 fps, 29.97 tbr, 90k tbn, 59.94 tbc (default)
    ...    Metadata:
    ...      handler_name    : VideoHandler
    ...    Stream #0:1(und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 125 kb/s (default)
    ...    Metadata:
    ...      handler_name    : SoundHandler'''
    >>> result = _parse_ffprobe_output(s)
    >>> print(json.dumps(result, indent=2, sort_keys=True).replace(', \n', ',\n'))
    {
      "duration": 1499.55,
      "streams": [
        {
          "fps": 29.97,
          "resolution": [
            [
              1920,
              1080
            ],
            "[SAR 1:1 DAR 16:9]"
          ],
          "type": "Video"
        },
        {
          "sample_rate": 44100,
          "type": "Audio"
        }
      ]
    }
    >>> s = '''Input #0, wav, from '1.wav':
    ...  Metadata:
    ...    encoder         : Lavf57.71.100
    ...  Duration: 00:05:19.51, bitrate: 1411 kb/s
    ...    Stream #0:0: Audio: pcm_s16le ([1][0][0][0] / 0x0001), 44100 Hz, 2 channels, s16, 1411 kb/s'''
    >>> result = _parse_ffprobe_output(s)
    >>> print(json.dumps(result, indent=2, sort_keys=True).replace(', \n', ',\n'))
    {
      "duration": 319.51,
      "streams": [
        {
          "sample_rate": 44100,
          "type": "Audio"
        }
      ]
    }
    """
    def _split_csv(s):
        ss = s.split(", ")
        result = []
        i = 0
        while i < len(ss):
            result.append(ss[i])
            while i < len(ss) - 1 and \
                    result[-1].count("(") != result[-1].count(")"):
                i += 1
                result[-1] = ", ".join((result[-1], ss[i]))
            i += 1
        return result
        
    result = {"streams": []}
    lines = inputstr.split("\n")
    rgx = r"Duration: (\d{2}):(\d{2}):(\d{2}).(\d{2})"
    while lines:
        line = lines.pop(0)
        m = re.search(rgx, line)
        if m:
            tp = list(map(int, m.group(1, 2, 3, 4)))
            result["duration"] = \
                tp[0] * 60 * 60 + tp[1] * 60 + tp[2] + tp[3] / 100.
            break
    #
    rgx = r"Stream #(\d+):(\d+)(?:\(\w+\))?: ([^:]+): (.*)$"
    strms_tmp = {}
    for line in lines:
        m = re.search(rgx, line)
        if not m:
            continue
        ifidx, strmidx, strmtype, rest = m.group(1, 2, 3, 4)
        if strmtype == "Video":
            spl = _split_csv(rest)
            resol = list(filter(lambda item: re.search(r"[1-9]\d*x[1-9]\d*", item), spl))[0]
            fps = list(filter(lambda item: re.search(r"[\d.]+ fps", item), spl))[0]
            strms_tmp[int(strmidx)] = {
                "type": strmtype,
                "resolution": [
                    list(map(int, s.split("x"))) if i == 0 else s
                    for i, s in enumerate(resol.partition(" ")[0::2])
                    ],
                "fps": float(fps.split(" ")[0]),
                }
        elif strmtype == "Audio":
            spl = _split_csv(rest)
            ar = list(filter(lambda item: re.search(r"\d+ Hz", item), spl))[0]
            strms_tmp[int(strmidx)] = {
                "type": strmtype,
                "sample_rate": int(re.match(r"(\d+) Hz", ar).group(1)),
                }
        #elif strmtype == "Subtitle"?
    for i in sorted(strms_tmp.keys()):
        result["streams"].append(strms_tmp[i])
    return result


def get_media_info(filename):
    """
    return the information extracted by ffprobe.
    """
    # If processing is progressed when there is no input file, exception
    # reporting is considerably troublesome. Therefore, we decide to check
    # existence in getatime to understand easily.
    os.path.getatime(filename)

    err = check_stderroutput(["ffprobe", "-hide_banner", filename])
    return _parse_ffprobe_output(err.decode("utf-8"))


def duration_to_hhmmss(duration):
    ss_h = duration // 3600
    ss_m = duration // 60
    ss_s = duration % 60
    return "%02d:%02d:%02d.%s" % (
        ss_h, ss_m, ss_s, ("%.3f" % duration).split(".")[1])


def media_to_mono_wave(
    video_file,
    out_dir,
    starttime_offset=0,  # -ss
    duration=0,  # -t
    sample_rate=48000,  # -ar
    ):
    """
    Convert the given media to monoral WAV by calling `ffmpeg`.
    """
    # If processing is progressed when there is no input file, exception
    # reporting is considerably troublesome. Therefore, we decide to check
    # existence in getatime to understand easily.
    os.path.getatime(video_file)

    _ffmpeg_ss_args = (None, None)
    ffmpeg_t_args = (None, None)
    if starttime_offset > 0:
        _ffmpeg_ss_args = (
            "-ss", duration_to_hhmmss(starttime_offset))
    if duration and duration > 0:
        ffmpeg_t_args = ("-t", "%d" % duration)

    track_name = os.path.basename(video_file)
    # !! CHECK TO SEE IF FILE IS IN UPLOADS DIRECTORY
    audio_output = track_name + "[%d-%d-%d]WAV.wav" % (
        starttime_offset, duration, sample_rate)

    output = os.path.join(out_dir, audio_output)
    if not os.path.exists(output):
        cmd = [
                "ffmpeg", "-hide_banner", "-y",
                _ffmpeg_ss_args[0], _ffmpeg_ss_args[1],
                ffmpeg_t_args[0], ffmpeg_t_args[1],
                "-i", "%s" % video_file,
                "-vn",
                "-ar", "%d" % sample_rate,
                "-ac", "1",
                "-f", "wav",
                "%s" % output
                ]
        #_logger.debug(cmd)
        check_call(cmd, stderr=open(os.devnull, 'w'))
    return output


if __name__ == '__main__':
    import doctest
    doctest.testmod()
