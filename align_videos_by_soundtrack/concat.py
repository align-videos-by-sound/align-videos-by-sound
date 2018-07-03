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

from .align import SyncDetector
from .communicate import check_call
from .ffmpeg_filter_graph import (
    Filter,
    ConcatWithGapFilterGraphBuilder,
    )
from .utils import check_and_decode_filenames


_logger = logging.getLogger(__name__)


def _build(args):
    chk = check_and_decode_filenames([args.base])
    if not chk:
        sys.exit(1)
    base = chk[0]

    targets = check_and_decode_filenames([args.splitted_earliest] + args.splitted)
    if not targets:
        sys.exit(1)

    a_filter_extra = json.loads(args.a_filter_extra) if args.a_filter_extra else {}
    v_filter_extra = json.loads(args.v_filter_extra) if args.v_filter_extra else {}

    vf = lambda i: ",".join(filter(None, [v_filter_extra.get(""), v_filter_extra.get("%d" % i)]))
    af = lambda i: ",".join(filter(None, [a_filter_extra.get(""), a_filter_extra.get("%d" % i)]))

    gaps = []
    width, height = 0, 0
    sample_rate = 0
    base_has_video = None
    start = 0
    with SyncDetector() as sd:
        for i in range(len(targets)):
            res = sd.align([base, targets[i]])
            gaps.append((start, res[0][1]["trim"] - start))
            start = res[0][1]["trim"] + (res[1][1]["orig_duration"] - res[1][1]["trim"])

            # detect resolution, etc.
            if base_has_video is None:
                ostrms_base = res[0][1]["orig_streams"]
                base_has_video = any([st["type"] == "Video" for st in ostrms_base])
            ostrms = res[1][1]["orig_streams"]
            for st in ostrms:
                if "resolution" in st:
                    new_w, new_h = st["resolution"][0]
                    width, height = max(width, new_w), max(height, new_h)
                elif "sample_rate" in st:
                    sample_rate = max(sample_rate, st["sample_rate"])

    bld = ConcatWithGapFilterGraphBuilder("c", w=width, h=height, sample_rate=sample_rate)
    for i in range(len(targets)):
        start, gap = gaps[i]
        if gap > 0:
            if not base_has_video or args.video_gap == "black":
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
        bld.add_video_content(i + 1, vf(i + 1))
        bld.add_audio_content(i + 1, af(i + 1))
    fc, vmap, amap = bld.build()
    return [base] + targets, fc, vmap, amap


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
        "splitted_earliest",
        help="""First video to be concatinated. \
Currently, both video stream and audio stream must be included.""")
    parser.add_argument(
        "splitted", nargs="+",
        help="""\
Videos to be concatinated. Arrange them in chronological order. \
When concatenating, if there is a gap which is detected by the "base" audio, \
this script fills it. However, even if there is overlap, \
this script does not complain anything, but it goes without \
saying that it's a "strange" movie. Currently, both video stream and audio \
stream must be included.""")
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
    args = parser.parse_args(args[1:])
    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)

    extra_ffargs = [
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"
        ]
    files, fc, vmap, amap = _build(args)
    maps = [vmap, amap]
    def _quote(s):
        if args.mode == "script_bash":
            import pipes
            return pipes.quote(s)
        return s
    ifile_args = list(chain.from_iterable(
            [('-i', _quote(f)) for f in files]))
    map_args = list(chain.from_iterable(
            [("-map", _quote(m)) for m in maps])) + [_quote(args.outfile)]
    #
    if args.mode == "script_bash":
        print("""\
#! /bin/sh

ffmpeg -y \\
  {} \\
  -filter_complex "
{}
" {} \\
  {}
""".format(" ".join(ifile_args),
           fc,
           " ".join(extra_ffargs),
           " ".join(map_args)))
    else:
        cmd = ["ffmpeg", "-y"]
        cmd.extend(ifile_args)
        cmd.extend(["-filter_complex", fc])
        cmd.extend(extra_ffargs)
        cmd.extend(map_args)

        check_call(cmd)

#
if __name__ == '__main__':
    main()
