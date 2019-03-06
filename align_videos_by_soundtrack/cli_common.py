# -*- coding: utf-8 -*-
#
"""
This module contains helpers for realizing common parts
in the CLI provided by this package
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import sys
import argparse
import textwrap
import json
import logging
import os

from .align_params import SyncDetectorSummarizerParams
from .edit_outparams import EditorOutputParams
from . import _cache
from .utils import json_loads


__all__ = [
    "logger_config",
    "AvstArgumentParser",
    ]

_logger = logging.getLogger(__name__)


# ##################################
#
# logging
#
def logger_config():
    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stderr,
        format="%(created)f|%(levelname)5s:%(module)s#%(funcName)s:%(message)s")


# ##################################
#
# argparse
#

# ----------------------
#
# create ArgumentParser and add common options
#
class AvstArgumentParser(argparse.ArgumentParser):
    def __init__(self, description=""):
        argparse.ArgumentParser.__init__(self, description=textwrap.dedent("""\
%s

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
""" % (description,
       SyncDetectorSummarizerParams.__doc__)),
                                         formatter_class=argparse.RawDescriptionHelpFormatter)

        self.add_argument(
            '--summarizer_params',
            type=str,
            help="""See above explanation.""")
        self.add_argument(
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
        self.add_argument(
            '--clear_cache',
            action="store_true",
            help='''Normally, this script stores the result in cache ("%s")
and use it if it already exists in cache. If you want to clear the cache
for some reason, specify this.''' % (
                _cache.cache_root_dir))

    # ---------------------------------------
    #
    # for editors
    #
    def editor_add_userelpath_argument(self):
        self.add_argument(
            "--relpath", action="store_true",
            help="Specifying whether to use relative path in generated script.")

    def editor_add_output_argument(self, default):
        self.add_argument(
            "-o", "--outfile", dest="outfile", default=default,
            help="Specifying the output file. (default: %(default)s)")

    def editor_add_output_params_argument(self, notice=""):
        default = EditorOutputParams()
        default = json.dumps(default.__dict__)
        self.add_argument(
            "--outparams",
            help="""Parameters for output. Pass in JSON format, 
in dictionary format. For example, '{"fps": 29.97, "sample_rate": 44100}'
etc.
 %s
 (default: %s).""" % (notice, default),
            default=default)

    def editor_add_mode_argument(self):
        self.add_argument(
            '--mode', choices=['script_bash', 'script_python', 'direct'], default='script_bash',
            help="""\
Switching whether to produce bash shellscript or to call ffmpeg directly. (default: %(default)s)""")

    def editor_add_filter_extra_arguments(self):
        self.add_argument(
            '--a_filter_extra', type=str,
            help="""\
Filter to add to the audio input stream. Pass in JSON format, in dictionary format
(stream by key, filter by value). For example, '{"1": "volume = 0.5", "2": "loudnorm"}' etc.
If the key is blank, it means all input streams. Only single input / single output
filters can be used.""")
        self.add_argument(
            '--v_filter_extra', type=str,
            help="""\
Filter to add to the video input stream. Pass in JSON format, in dictionary format
(stream by key, filter by value). For example, '{"1": "boxblur=luma_radius=2:luma_power=1"}' etc.
If the key is blank, it means all input streams. Only single input / single output
filters can be used.""")

    def editor_add_extra_ffargs_arguments(self):
        self.add_argument(
            '--v_extra_ffargs', type=str,
            default=json.dumps(["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]),
            help="""\
Additional arguments to ffmpeg for output video streams. Pass list in JSON format. \
(default: '%(default)s')""")
        self.add_argument(
            '--a_extra_ffargs', type=str,
            default=json.dumps([]),
            help="""\
Additional arguments to ffmpeg for output audio streams. Pass list in JSON format. \
(default: '%(default)s')""")

    # ----------------------
    #
    # interpret common options
    #
    def parse_args(self, args=None, namespace=None):
        args = argparse.ArgumentParser.parse_args(self, args, namespace)
        #
        if args.known_delay_map:
            known_delay_map_orig = json_loads(args.known_delay_map)
            known_delay_map = {}
            for k in known_delay_map_orig.keys():
                nk = os.path.abspath(k)
                known_delay_map[nk] = known_delay_map_orig[k]
                known_delay_map[nk]["base"] = os.path.abspath(known_delay_map_orig[k]["base"])
            args.known_delay_map = known_delay_map
        #
        args.summarizer_params = SyncDetectorSummarizerParams.from_json(
            args.summarizer_params)
        #
        if hasattr(args, "outparams"):
            args.outparams = EditorOutputParams.from_json(args.outparams)
        if hasattr(args, "a_filter_extra"):
            args.a_filter_extra = json_loads(args.a_filter_extra) if args.a_filter_extra else {}
        if hasattr(args, "v_filter_extra"):
            args.v_filter_extra = json_loads(args.v_filter_extra) if args.v_filter_extra else {}
        #
        if hasattr(args, "a_extra_ffargs"):
            args.a_extra_ffargs = json_loads(args.a_extra_ffargs) if args.a_extra_ffargs else []
        if hasattr(args, "v_extra_ffargs"):
            args.v_extra_ffargs = json_loads(args.v_extra_ffargs) if args.v_extra_ffargs else []
        #
        return args



if __name__ == '__main__':
    import doctest
    doctest.testmod()
