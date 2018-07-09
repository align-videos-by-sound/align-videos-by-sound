#! /bin/env python
# -*- coding: utf-8 -*-
"""
This module is intended as an example of one application of
"align_videos_by_soundtrack.align". For a concert movie, now,
there is one movie that shoots the whole event and a movie
divided into two by stopping shooting (or cutting by editing)
once. This script combines the latter with filling the gap,
based on the former sound tracks.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import sys
import logging
import json
from itertools import chain

import numpy as np

from .align import SyncDetector
from .communicate import call_ffmpeg_with_filtercomplex
from .ffmpeg_filter_graph import (
    Filter,
    ConcatWithGapFilterGraphBuilder,
    )
from .utils import check_and_decode_filenames
from . import _cache


_logger = logging.getLogger(__name__)


def _build(args):
    base = check_and_decode_filenames(
        [args.base], exit_if_error=True)[0]
    targets = check_and_decode_filenames(
        args.splitted, min_num_files=2, exit_if_error=True)

    a_filter_extra = json.loads(args.a_filter_extra) if args.a_filter_extra else {}
    v_filter_extra = json.loads(args.v_filter_extra) if args.v_filter_extra else {}

    vf = lambda i: ",".join(filter(None, [v_filter_extra.get(""), v_filter_extra.get("%d" % i)]))
    af = lambda i: ",".join(filter(None, [a_filter_extra.get(""), a_filter_extra.get("%d" % i)]))

    gaps = []
    #
    einf = []
    with SyncDetector(dont_cache=args.dont_cache) as sd:
        start = 0
        known_delay_ge_map = {}
        for i in range(len(targets)):
            res = sd.align(
                [base, targets[i]],
                known_delay_ge_map=known_delay_ge_map)
            gaps.append((start, res[0]["trim"] - start))
            start = res[0]["trim"] + (res[1]["orig_duration"] - res[1]["trim"])
            known_delay_ge_map[0] = start
            if i == 0:
                einf.append(res[0])
            einf.append(res[1])
    #
    qual = SyncDetector.summarize_stream_infos(einf)
    targets_have_video = any(qual["has_video"][1:])
    bld = ConcatWithGapFilterGraphBuilder(
        "c",
        w=qual["max_width"],
        h=qual["max_height"],
        fps=qual["max_fps"],
        sample_rate=qual["max_sample_rate"])
    for i in range(len(targets)):
        start, gap = gaps[i]
        if gap > 0 and (
            not np.isclose(start, 0) or args.start_gap != "omit"):

            if targets_have_video or qual["has_video"][0]:
                if not qual["has_video"][0] or args.video_gap == "black":
                    bld.add_video_gap(gap)
                else:
                    fv = Filter()
                    fv.add_filter("trim", "%.3f" % start, "%.3f" % (start + gap))
                    fv.add_filter("setpts", "PTS-STARTPTS")
                    bld.add_video_content(0, ",".join(
                            list(filter(None, [vf(0), fv.to_str()]))))
            #
            if args.audio_gap == "silence":
                bld.add_audio_gap(gap)
            else:
                fa = Filter()
                fa.add_filter("atrim", "%.3f" % start, "%.3f" % (start + gap))
                fa.add_filter("asetpts", "PTS-STARTPTS")
                bld.add_audio_content(0, ",".join(
                        list(filter(None, [af(0), fa.to_str()]))))

        if targets_have_video or qual["has_video"][0]:
            if qual["has_video"][i + 1]:
                bld.add_video_content(i + 1, vf(i + 1))
            else:
                # wav, mp3, etc...
                bld.add_video_gap(einf[i + 1]["orig_duration"])
        bld.add_audio_content(i + 1, af(i + 1))
    fc, vmap, amap = bld.build()
    return [base] + targets, fc, [vmap], [amap]


def main(args=sys.argv):
    import argparse

    parser = argparse.ArgumentParser(description="""\
For a concert movie, now, \
there is one movie that shoots the whole event and a movie \
divided into two by stopping shooting (or cutting by editing) \
once. This script combines the latter with filling the gap, \
based on the former sound tracks.""")
    parser.add_argument(
        "base",
        help="""\
The media file which contains at least audio, \
which becomes a base of synchronization of files to be concatinated.""")
    parser.add_argument(
        "splitted", nargs="+",
        help="""\
Videos (at least two files) to be concatinated. Arrange them in \
chronological order. When concatenating, if there is a gap which \
is detected by the "base" audio, this script fills it. However, \
even if there is overlap, this script does not complain anything, \
but it goes without saying that it's a "strange" movie.""")
    parser.add_argument(
        "-o", "--outfile", dest="outfile", default="concatenated.mp4",
        help="Specifying the output file. (default: %(default)s)")
    parser.add_argument(
        '--mode', choices=['script_bash', 'direct'], default='script_bash',
        help="""\
Switching whether to produce bash shellscript or to call ffmpeg directly. (default: %(default)s)""")
    #
    #####
    parser.add_argument(
        '--audio_gap', choices=['silence', 'base'], default='base',
        help="""\
Switching whether to use no audio or to use base audio as gap. (default: %(default)s)""")
    #
    parser.add_argument(
        '--a_filter_extra', type=str,
        help="""\
Filter to add to the audio input stream. Pass in JSON format, in dictionary format \
(stream by key, filter by value). For example, '{"1": "volume = 0.5", "2": "loudnorm"}' etc. \
The key "0" is of base audio media. \
If the key is blank, it means all input streams. Only single input / single output \
filters can be used.""")
    ###
    parser.add_argument(
        '--video_gap', choices=['black', 'base'], default='base',
        help="""\
Switching whether to use no video or to use base video as gap. (default: %(default)s)""")
    #
    parser.add_argument(
        '--v_filter_extra', type=str,
        help="""\
Filter to add to the video input stream. Pass in JSON format, in dictionary format \
(stream by key, filter by value). For example, '{"1": "boxblur=luma_radius=2:luma_power=1"}' etc. \
The key "0" is of base audio media. \
If the key is blank, it means all input streams. Only single input / single output \
filters can be used.""")
    #####
    parser.add_argument(
        '--start_gap', choices=['omit', 'pad'], default='omit',
        help="""\
Controling whether to align the start position with `base` or not. \
The default is "do not align" (`omit`) because it is not normally suitable for the \
purpose of `concatanate`.""")
    #####
    parser.add_argument(
        '--v_extra_ffargs', type=str,
        default=json.dumps(["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]),
        help="""\
Additional arguments to ffmpeg for output video streams. Pass list in JSON format. \
(default: '%(default)s')""")
    parser.add_argument(
        '--a_extra_ffargs', type=str,
        default=json.dumps([]),
        help="""\
Additional arguments to ffmpeg for output audio streams. Pass list in JSON format. \
(default: '%(default)s')""")
    #####
    parser.add_argument(
        '--dont_cache',
        action="store_true",
        help='''Normally, this script stores the result in cache ("%s"). \
If you hate this behaviour, specify this option.''' % (
            _cache.cache_root_dir))
    #####
    args = parser.parse_args(args[1:])
    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stderr,
        format="%(created)f|%(levelname)5s:%(module)s#%(funcName)s:%(message)s")

    files, fc, vmap, amap = _build(args)
    v_extra_ffargs = json.loads(args.v_extra_ffargs) if vmap else []
    a_extra_ffargs = json.loads(args.a_extra_ffargs) if amap else []
    call_ffmpeg_with_filtercomplex(
        args.mode,
        files,
        fc,
        v_extra_ffargs + a_extra_ffargs,
        zip(vmap, amap),
        [args.outfile])


#
if __name__ == '__main__':
    main()
