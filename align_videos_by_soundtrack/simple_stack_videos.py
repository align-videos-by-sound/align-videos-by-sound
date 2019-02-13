#! /bin/env python
# -*- coding: utf-8 -*-
"""
This module is intended as an example of one application of
"align_videos_by_soundtrack.align". Suppose that a certain concert is
shot by multiple people from multiple angles. In most cases, shooting
start and shooting end time have individual differences. It is now time
for "align_videos_by_soundtrack.align" to come. Based on the information
obtained from "align_videos_by_soundtrack.align", this script combines
movies of multiple angles in a tile shape with "hstack" and "vstack".
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import json
import sys
import os
import logging

import numpy as np

from .align import SyncDetector
from .communicate import call_ffmpeg_with_filtercomplex
from .ffmpeg_filter_graph import Filter, ConcatWithGapFilterGraphBuilder
from .utils import check_and_decode_filenames
from . import cli_common


_logger = logging.getLogger(__name__)


class _StackVideosFilterGraphBuilder(object):
    def __init__(self, shape=(2, 2), w=960, h=540, fps=29.97, sample_rate=44100):
        self._shape = shape
        self._builders = []
        for i in range(shape[0] * shape[1]):
            self._builders.append(
                ConcatWithGapFilterGraphBuilder(i, w, h, fps, sample_rate))

    def set_paddings(self, idx, pre, post, v_filter_extra, a_filter_extra):
        self._builders[idx].add_video_gap(pre)
        self._builders[idx].add_audio_gap(pre)
        self._builders[idx].add_video_content(idx, v_filter_extra)
        self._builders[idx].add_audio_content(idx, a_filter_extra)
        self._builders[idx].add_video_gap(post)
        self._builders[idx].add_audio_gap(post)

    def build_each_streams(self):
        result = []
        _r = []
        len_stacks = len(self._builders)
        for i in range(len_stacks):
            _r.append(self._builders[i].build())
            result.append(_r[i][0])

        # filters string array, video maps, audio maps
        return result, [_ri[1] for _ri in _r], [_ri[2] for _ri in _r]

    def build_stack_videos(self, ivmaps):
        result = []

        ovmaps = ['[v]']
        # stacks for video
        fvstack = Filter()
        if self._shape[0] > 1:
            for i in range(self._shape[1]):
                fhstack = Filter()
                fhstack.iv.extend(ivmaps[i * self._shape[0]:(i + 1) * self._shape[0]])
                inputs = len(ivmaps[
                        i * self._shape[0]:(i + 1) * self._shape[0]])
                fhstack.add_filter(
                    "hstack",
                    inputs=inputs,
                    shortest="1")
                olab = "[{}v]".format("%d" % (i + 1) if self._shape[1] > 1 else "")
                fhstack.ov.append(olab)
                result.append(fhstack.to_str())

                fvstack.iv.append(olab)
        else:
            fvstack.iv.extend(ivmaps)

        if self._shape[1] > 1:
            # vstack
            fvstack.add_filter(
                "vstack", inputs=self._shape[1], shortest="1")
            fvstack.ov.append("[v]")
            result.append(fvstack.to_str())

        return result, ovmaps

    def build_amerge_audio(self, iamaps):
        #
        result = []

        # stacks for audio (amerge)
        nch = 2
        weight = 1 - np.array(
            [i // self._shape[0] for i in range(self._shape[0] * nch)])
        ch = [
            " + ".join([
                    "c%d" % (i)
                    for i in range(len(iamaps) * nch)
                    if weight[i % (self._shape[0] * nch)]]),
            " + ".join([
                    "c%d" % (i)
                    for i in range(len(iamaps) * nch)
                    if (1 - weight)[i % (self._shape[0] * nch)]])
            ]
        result.append("""\
{}
amerge=inputs={},
pan=stereo|\\
    c0 < {} |\\
    c1 < {}
[a]""".format("".join(iamaps),
              len(self._builders), ch[0], ch[1],))

        #
        return result, ['[a]']

    def build_multi_streams_audio(self, iamaps):
            result = []
            result.append("""\
    {}
    amerge=inputs={}
    [a]""".format("".join(iamaps),
                len(self._builders),))

            #
            return result, ['[a]']


def _build(args):
    shape = json.loads(args.shape) if args.shape else (2, 2)
    files = check_and_decode_filenames(
        args.files,
        min_num_files=2, exit_if_error=True)
    if len(files) < shape[0] * shape[1]:
        files = files + [files[i % len(files)]
                         for i in range(shape[0] * shape[1] - len(files))]
    else:
        files = files[:shape[0] * shape[1]]
    #
    a_filter_extra = args.a_filter_extra
    v_filter_extra = args.v_filter_extra
    #
    with SyncDetector(
        params=args.summarizer_params,
        clear_cache=args.clear_cache) as det:

        ares = det.align(
            files,
            known_delay_map=args.known_delay_map)
    qual = SyncDetector.summarize_stream_infos(ares)
    outparams = args.outparams
    outparams.fix_params(qual)

    b = _StackVideosFilterGraphBuilder(
        shape=shape,
        w=args.w,
        h=args.h,
        fps=outparams.fps,
        sample_rate=outparams.sample_rate)

    for i, inf in enumerate(ares):
        pre, post = inf["pad"], inf["pad_post"]
        if not (pre > 0 and post > 0):
            # FIXME:
            #  In this case, if we don't add paddings, we'll encount the following:
            #    [AVFilterGraph @ 0000000003146500] The following filters could not
            #choose their formats: Parsed_amerge_48
            #    Consider inserting the (a)format filter near their input or output.
            #    Error reinitializing filters!
            #    Failed to inject frame into filter network: I/O error
            #    Error while processing the decoded data for stream #3:0
            #    Conversion failed!
            #
            #  Just by adding padding just like any other stream, it seems we can
            #  avoid it, so let's add meaningless padding as a workaround.
            post = post + 1.0

        vf = ",".join(filter(None, [v_filter_extra.get(""), v_filter_extra.get("%d" % i)]))
        af = ",".join(filter(None, [a_filter_extra.get(""), a_filter_extra.get("%d" % i)]))
        b.set_paddings(i, pre, post, vf, af)

    #
    filters = []
    r0, vm0, am0 = b.build_each_streams()
    filters.extend(r0)
    if args.video_mode == "stack" and args.audio_mode != "individual":
        r1, vm1 = b.build_stack_videos(vm0)
        filters.extend(r1)
    else:
        vm1 = vm0
    if args.audio_mode == "amerge" and args.video_mode != "individual":
        r2, am = b.build_amerge_audio(am0)
        filters.extend(r2)
    elif args.audio_mode == "multi_streams" and args.video_mode != "individual":
        r2, am = b.build_multi_streams_audio(am0)
        filters.extend(r2)
    else:
        am = am0
    #
    filter_complex = ";\n\n".join(filters)
    #
    return files, filter_complex, (vm1, am)


def main(args=sys.argv):
    parser = cli_common.AvstArgumentParser(description="""\
Suppose that a certain concert is shot by multiple people from multiple angles.
In most cases, shooting start and shooting end time have individual differences.
This program combines movies of multiple angles in a tile shape with "hstack" and "vstack",
based on sound track synchronization. Although it is a program for the main object
to arrange tile-like and simultaneous playback, it is possible to do a little
different thing from this. See the option description.""")
    parser.add_argument(
        "files", nargs="+",
        help="The media files which contains both video and audio.")
    parser.editor_add_output_argument(default="merged.mp4")
    parser.editor_add_output_params_argument(
        notice="Note: In this script, width and height are ignored.")
    parser.editor_add_mode_argument()
    #####
    parser.add_argument(
        '--audio_mode', choices=['amerge', 'multi_streams', 'individual'], default='amerge',
        help="""\
Switching whether to merge audios or to keep each as multi streams, or
to pad each into the corresponding individual output file. --audio_mode='individual'
implies --video_mode='individual'. (default: %(default)s)""")
    #
    parser.add_argument(
        '--video_mode', choices=['stack', 'multi_streams', 'individual'], default='stack',
        help="""\
Switching whether to stack videos or to keep each as multi streams, or
to pad each into the corresponding individual output file. --video_mode='individual'
implies --audio_mode='individual'. (default: %(default)s)""")
    #
    parser.editor_add_filter_extra_arguments()
    #####
    parser.add_argument(
        '--shape', type=str, default="[2, 2]",
        help="The shape of the tile, like '[2, 2]'. (default: %(default)s)")
    parser.add_argument(
        '--width-per-cell', dest="w", type=int, default=960,
        help="Width of the cell. (default: %(default)d)")
    parser.add_argument(
        '--height-per-cell', dest="h", type=int, default=540,
        help="Height of the cell. (default: %(default)d)")
    #####
    parser.editor_add_extra_ffargs_arguments()
    #####
    args = parser.parse_args(args[1:])
    cli_common.logger_config()
    
    files, fc, (vmap, amap) = _build(args)
    if args.video_mode == 'individual' or args.audio_mode == 'individual':
        outbase, outext = os.path.splitext(args.outfile)
        outfiles = ["{}_{:02d}{}".format(outbase, i, outext)
                    for i in range(len(vmap))]
    else:
        outfiles = [args.outfile]

    call_ffmpeg_with_filtercomplex(
        args.mode,
        files,
        fc,
        vmap, amap,
        args.v_extra_ffargs, args.a_extra_ffargs,
        outfiles)


#
if __name__ == '__main__':
    main()
