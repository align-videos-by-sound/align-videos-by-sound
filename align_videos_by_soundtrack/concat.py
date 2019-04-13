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

import numpy as np

from .align import SyncDetector
from .communicate import call_ffmpeg_with_filtercomplex
from .ffmpeg_filter_graph import (
    Filter,
    ConcatWithGapFilterGraphBuilder,
    )
from .utils import check_and_decode_filenames
from . import cli_common


_logger = logging.getLogger(__name__)


def _build(args):
    base = check_and_decode_filenames(
        [args.base], exit_if_error=True)[0]
    targets = check_and_decode_filenames(
        args.splitted, min_num_files=1, exit_if_error=True)
    known_delay_map = args.known_delay_map

    a_filter_extra = args.a_filter_extra
    v_filter_extra = args.v_filter_extra

    vf = lambda i: ",".join(filter(None, [v_filter_extra.get(""), v_filter_extra.get("%d" % i)]))
    af = lambda i: ",".join(filter(None, [a_filter_extra.get(""), a_filter_extra.get("%d" % i)]))

    gaps = []
    #
    einf = []
    start = 0
    base_dur = 0
    with SyncDetector(
        params=args.summarizer_params,
        clear_cache=args.clear_cache) as sd:

        upd = base not in known_delay_map
        for i in range(len(targets)):
            if upd and start:
                known_delay_map.update({
                        base: {
                            "base": targets[i],
                            "min": start
                            }
                        })
            res = sd.align(
                [base, targets[i]],
                known_delay_map=known_delay_map)
            base_dur = res[0]["orig_duration"]
            gaps.append((start, res[0]["trim"] - start))
            start = res[0]["trim"] + (
                res[1]["orig_duration"] - res[1]["trim"])
            if i == 0:
                einf.append(res[0])
            einf.append(res[1])
    end_pad = False
    if start < base_dur:
        end_pad = True
        gaps.append((start, base_dur - start))
    #
    qual = SyncDetector.summarize_stream_infos(einf)
    targets_have_video = any(qual["has_video"][1:])
    outparams = args.outparams
    outparams.fix_params(qual)
    bld = ConcatWithGapFilterGraphBuilder(
        "c",
        w=outparams.width,
        h=outparams.height,
        fps=outparams.fps,
        sample_rate=outparams.sample_rate)
    def _add_gap(start, gap):
        if gap > 0 and (
            not np.isclose(start, 0) or args.start_gap != "omit"):

            if targets_have_video or qual["has_video"][0]:
                if not qual["has_video"][0] or args.video_gap == "black":
                    bld.add_video_gap(gap)
                else:
                    fv = Filter()
                    fv.add_filter(
                        "trim", "%.3f" % start,
                        "%.3f" % (start + gap))
                    fv.add_filter("setpts", "PTS-STARTPTS")
                    bld.add_video_content(0, ",".join(
                            list(filter(None, [vf(0), fv.to_str()]))))
            #
            if args.audio_gap == "silence":
                bld.add_audio_gap(gap)
            else:
                fa = Filter()
                fa.add_filter(
                    "atrim", "%.3f" % start,
                    "%.3f" % (start + gap))
                fa.add_filter("asetpts", "PTS-STARTPTS")
                bld.add_audio_content(0, ",".join(
                        list(filter(None, [af(0), fa.to_str()]))))
    for i in range(len(targets)):
        start, gap = gaps[i]
        _add_gap(start, gap)
        if targets_have_video or qual["has_video"][0]:
            if qual["has_video"][i + 1]:
                bld.add_video_content(i + 1, vf(i + 1))
            else:
                # wav, mp3, etc...
                bld.add_video_gap(einf[i + 1]["orig_duration"])
        bld.add_audio_content(i + 1, af(i + 1))
    if end_pad and args.end_gap == "pad":
        start, gap = gaps[len(targets)]
        _add_gap(start, gap)
    try:
        fc, vmap, amap = bld.build()
    except Exception as e:
        _logger.warning("Nothing to do.")
        sys.exit(0)
    return [base] + targets, fc, [vmap], [amap]


def main(args=sys.argv):
    parser = cli_common.AvstArgumentParser(description="""
For a concert movie, now, there is one movie that shoots the
whole event and a movie divided into two by stopping shooting
(or cutting by editing) once. This script combines the latter
with filling the gap, based on the former sound tracks.""")
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
    parser.editor_add_userelpath_argument()
    parser.editor_add_output_argument(default="concatenated.mp4")
    parser.editor_add_output_params_argument()
    parser.editor_add_mode_argument()
    #
    #####
    parser.add_argument(
        '--audio_gap', choices=['silence', 'base'], default='base',
        help="""\
Switching whether to use no audio or to use base audio as gap. (default: %(default)s)""")
    #
    parser.add_argument(
        '--video_gap', choices=['black', 'base'], default='base',
        help="""\
Switching whether to use no video or to use base video as gap. (default: %(default)s)""")
    #
    parser.editor_add_filter_extra_arguments()
    parser.add_argument(
        '--start_gap', choices=['omit', 'pad'],
        help="""\
Controling whether to align the start position with `base` or not. \
The default is "do not align" (`omit`) because it is not normally suitable for the \
purpose of `concatanate`. The default is "omit" if there are two or more media \
specified as "splitted". If there is only one media specified as "splitted", \
the default is "pad", assuming your goal is to fill in the leading gap.""")
    parser.add_argument(
        '--end_gap', choices=['omit', 'pad'],
        help="""\
Controling whether to align the end position with `base` or not. \
The default is "do not align" (`omit`) because it is not normally suitable for the \
purpose of `concatanate`. The default is "omit" if there are two or more media \
specified as "splitted". If there is only one media specified as "splitted", \
the default is "pad", assuming your goal is to fill in the leading gap.""")
    #####
    parser.editor_add_extra_ffargs_arguments()
    #####
    args = parser.parse_args(args[1:])
    if not args.start_gap:
        args.start_gap = "omit" if len(args.splitted) > 1 else "pad"
    if not args.end_gap:
        args.end_gap = "omit" if len(args.splitted) > 1 else "pad"
    cli_common.logger_config()

    files, fc, vmap, amap = _build(args)
    call_ffmpeg_with_filtercomplex(
        args.mode,
        files,
        fc,
        vmap, amap,
        args.v_extra_ffargs, args.a_extra_ffargs,
        [args.outfile],
        args.relpath)


#
if __name__ == '__main__':
    main()
