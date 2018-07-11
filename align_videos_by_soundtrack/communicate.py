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
from itertools import chain

import scipy.io.wavfile

__all__ = [
    "check_call", "check_stderroutput",
    "read_audio",
    "get_media_info",
    "media_to_mono_wave",
    "duration_to_hhmmss",
    "parse_time",
    ]

_logger = logging.getLogger(__name__)


if hasattr("", "decode"):  # python 2
    def _encode(s):
        return s.encode(sys.getfilesystemencoding())
else:
    def _encode(s):
        return s


# ##################################
#
# low-level APIs
#

class pipes_quote(object):
    def __init__(self, needs_to_quote=True):
        self._needs_to_quote = needs_to_quote

    def __call__(self, s):
        if self._needs_to_quote:
            import pipes
            return pipes.quote(s)
        return s

    def map(self, iterable):
        for iter in iterable:
            yield self.__call__(iter)

        
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


def duration_to_hhmmss(duration):
    ss_h = duration // 3600
    ss_m = duration // 60
    ss_s = duration % 60
    return "%02d:%02d:%02d.%s" % (
        ss_h, ss_m, ss_s, ("%.3f" % duration).split(".")[1])


def parse_time(s):
    """
    >>> print("%.3f" % parse_time(3.2))
    3.200
    >>> print("%.3f" % parse_time(3))
    3.000
    >>> print("%.3f" % parse_time("00:00:01"))
    1.000
    >>> print("%.3f" % parse_time("00:00:01.3"))
    1.300
    >>> print("%.3f" % parse_time("00:00:01.34"))
    1.340
    >>> print("%.3f" % parse_time("00:00:01.345"))
    1.345
    >>> print("%.3f" % parse_time("00:01:01.345"))
    61.345
    >>> print("%.3f" % parse_time("02:01:01.345"))
    7261.345
    """
    try:
        return float(s)
    except ValueError:
        rgx = r"(\d+):([0-5]\d):([0-5]\d)(\.\d+)?"
        m = re.match(rgx, s)
        if not m:
            raise ValueError("'{}' is not valid time.".format(s))
        hms = list(map(int, m.group(1, 2, 3)))
        ss = m.group(4)
        ss = ss[1:] if ss else "0"

        result = hms[0] * 60 * 60 + hms[1] * 60 + hms[2]
        result += int(ss) / (10**len(ss))
        return result


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
    rgx = r"Duration: (\d+:\d{2}:\d{2}\.\d+)"
    while lines:
        line = lines.pop(0)
        m = re.search(rgx, line)
        if m:
            result["duration"] = parse_time(m.group(1))
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


def _summarize_streams(streams):
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
    >>> result = _summarize_streams(_parse_ffprobe_output(s)["streams"])
    >>> print(json.dumps(result, indent=2, sort_keys=True).replace(', \n', ',\n'))
    {
      "max_fps": 29.97,
      "max_resol_height": 1080,
      "max_resol_width": 1920,
      "max_sample_rate": 44100,
      "num_audio_streams": 1,
      "num_video_streams": 1
    }
    >>> s = '''Input #0, wav, from '1.wav':
    ...  Metadata:
    ...    encoder         : Lavf57.71.100
    ...  Duration: 00:05:19.51, bitrate: 1411 kb/s
    ...    Stream #0:0: Audio: pcm_s16le ([1][0][0][0] / 0x0001), 44100 Hz, 2 channels, s16, 1411 kb/s'''
    >>> result = _summarize_streams(_parse_ffprobe_output(s)["streams"])
    >>> print(json.dumps(result, indent=2, sort_keys=True).replace(', \n', ',\n'))
    {
      "max_fps": 0.0,
      "max_resol_height": 0,
      "max_resol_width": 0,
      "max_sample_rate": 44100,
      "num_audio_streams": 1,
      "num_video_streams": 0
    }
    """
    result = dict(
        max_resol_width=0,
        max_resol_height=0,
        max_sample_rate=0,
        max_fps=0.0,
        num_video_streams=0,
        num_audio_streams=0)

    result["num_video_streams"] = sum(
        [st["type"] == "Video" for st in streams])
    result["num_audio_streams"] = sum(
        [st["type"] == "Audio" for st in streams])
    for st in streams:
        if st["type"] == "Video":
            new_w, new_h = st["resolution"][0]
            result["max_resol_width"] = max(
                result["max_resol_width"], new_w)
            result["max_resol_height"] = max(
                result["max_resol_height"], new_h)
            if "fps" in st:
                result["max_fps"] = max(
                    result["max_fps"], st["fps"])
        elif st["type"] == "Audio":
            result["max_sample_rate"] = max(
                result["max_sample_rate"], st["sample_rate"])

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
    result = _parse_ffprobe_output(err.decode("utf-8"))
    result["streams_summary"] = _summarize_streams(result["streams"])
    return result


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


def call_ffmpeg_with_filtercomplex(
    mode,
    inputfiles,
    filter_complex,
    extra_ffargs,
    maps,  # [("[v0]", "[a0]"), ("[v1]", "[a1]"), ("[v2]", "[a2]"), ...]
    outfiles):
    """
    Call ffmpeg or print a `bash` script.

    Calling ffmpeg is complicated, such as extremely delicate argument order,
    or there are also too flexible aliases, and enormous variation calling
    is possible if including up to deprecated options. but if it is called
    only by `-filter_complex` and` -map`, it is almost the same way of calling it.
    """
    ifile_args = chain.from_iterable([('-i', f) for f in inputfiles])
    if len(outfiles) > 1:
        map_args = []
        for zi in zip(maps, outfiles):
            map_args.extend(chain.from_iterable([("-map", m) for m in zi[0] if m]))
            map_args.extend(extra_ffargs)
            map_args.append(zi[1])
    else:
        map_args = []
        for mi in maps:
            map_args.extend(chain.from_iterable([("-map", m) for m in mi if m]))
        map_args.extend(extra_ffargs)
        map_args.append(outfiles[0])
    #
    if mode == "script_bash":
        _quote = pipes_quote()
        try:
            buf = sys.stdout.buffer
        except AttributeError:
            buf = sys.stdout
        buf.write("""\
#! /bin/sh
# -*- coding: utf-8 -*-

ffmpeg -y \\
  {} \\
  -filter_complex "
{}
" {}
""".format(" ".join(_quote.map(ifile_args)),
           filter_complex,
           " ".join(_quote.map(map_args))).encode("utf-8"))
    else:
        cmd = ["ffmpeg", "-y"]
        cmd.extend(ifile_args)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(map_args)

        check_call(cmd)


if __name__ == '__main__':
    import doctest
    doctest.testmod()
