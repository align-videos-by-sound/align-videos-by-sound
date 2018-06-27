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
import re
import logging

import scipy.io.wavfile

__all__ = [
    "check_call", "check_stderroutput",
    "read_audio",
    "get_media_info",
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
    return map(_encode, filter(None, *cmd))

    
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
            retcode, cmd, output=stderr_output)
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
    rate, data = scipy.io.wavfile.read(audio_file)  # Return the sample rate (in samples/sec) and data from a WAV file
    return data, rate


def get_media_info(filename):
    """
    return the information extracted by ffprobe.

    for now, this function extracts only its duration.
    """
    err = check_stderroutput(["ffprobe", filename])
    rgx = r"Duration: (\d{2}):(\d{2}):(\d{2}).(\d{2})"
    tp = list(
        map(int,
            re.search(
                rgx,
                err.decode("utf-8")).group(1, 2, 3, 4)))
    return {
        "duration": tp[0] * 60 * 60 + tp[1] * 60 + tp[2] + tp[3] / 100.,
        }
