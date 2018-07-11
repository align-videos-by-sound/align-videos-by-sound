#! /bin/env python
# -*- coding: utf-8 -*-
"""
This module is intended as an example of one application of
"align_videos_by_soundtrack.align". What this script does is
quite similar to `concat_videos_by_sound_track`, but it does
a bit more general tasks. Suppose there is a main unedited
movie, there are multiple sub movie materials you want to insert
into it. With this script, these materials can be superimposed or
replaced at specific times. Unlike video editing software with a
higher GUI, WYSWYG editing is not possible and there are no effect
functions, but by using this script it is easy to insert material without
being aware of synchronization point.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import json
import sys
import os
import io
from copy import deepcopy
from itertools import chain
import logging

import numpy as np

from .align import SyncDetector
from .communicate import parse_time, call_ffmpeg_with_filtercomplex
from .ffmpeg_filter_graph import Filter
from .utils import (
    check_and_decode_filenames,
    json_load,
    json_loads,
    validate_type_one_by_template,
    validate_dict_one_by_template
    )
#from . import _cache


_logger = logging.getLogger(__name__)


_sample_editinfo = """\
{
    "inputs": {
        "main": {
            "file": "main.mp4",
            "v_extra_filter": "",
            "a_extra_filter": "loudnorm"
        },
        "sub": [
            {
                "file": "sub1.mp4",
                "v_extra_filter": "",
                "a_extra_filter": ""
            },
            {
                "file": "sub2.mp4",
                "v_extra_filter": "boxblur=luma_radius=2:luma_power=1",
                "a_extra_filter": ""
            },
            {
                "file": "sub3.mp4",
                "v_extra_filter": "",
                "a_extra_filter": "volume=0.5"
            }
        ]
    },
    "intercuts": [
        {
            "sub_idx": 1,  /* in this example case, it means "sub2.mp4" */
            "start_time": "00:04:30.00",  /* or float seconds like 30.2 */
            "end_time": "00:04:49.00",
            "time_origin": "sub",  /* or "main" */
            "video_mode": "overlay",  /* or "blend" or "select" */

            /*
             * If video_mode is "overlay", "video_mode_params"
             * is like this:
             */
            "video_mode_params": [
                {
                    "mode": "sub_top",  /* or "sub_bottom" */

                    /*
                     * cropping, or scaling to top layer
                     */
                    "cropping": "crop=2/3*in_w:2/3*in_h, scale=480:-1",

                    /*
                     * see https://ffmpeg.org/ffmpeg-filters.html#overlay-1
                     */
                    "overlay": "W-w-50:h/2+50",

                    /*
                     * partner layer. specify "main", or sub_idx like 1.
                     * When omitting, this script follows the previous
                     * segment.
                     */
                    "partner_layer": "main"
                }
            ],
            "audio_mode": "select",  /* or "amerge", or "amix" */

            /*
             * If audio_mode is "select", you can specify "main", "sub", or
             * idx directly like [1].
             */
            "audio_mode_params": ["main"]
        },
        {
            "sub_idx": 2,
            "start_time": "00:07:13.00",
            "end_time": "00:07:57.00",
            "time_origin": "main",

            "video_mode": "select",

            /*
             * If video_mode is "select", you can specify "main", "sub", or
             * idx directly like [1].
             */
            "video_mode_params": ["sub"],

            "audio_mode": "select",
            "audio_mode_params": ["main"]
        },
        {
            "sub_idx": 1,
            "start_time": "00:15:20.00",
            "end_time": "00:20:30.00",
            "time_origin": "main",
            "video_mode": "select",
            "video_mode_params": [],

            "audio_mode": "amerge",

            /*
             * If audio_mode is "amerge" or "amix", you can specify like
             * [1, 2, 3] or ["main", "sub"], etc.
             */
            "audio_mode_params": [1, 2]
        },
        {
            "sub_idx": 2,
            "start_time": "00:21:10.00",
            "end_time": "00:22:30.00",
            "time_origin": "sub",
            "video_mode": "select",
            "video_mode_params": [],
            "audio_mode": "select",
            "audio_mode_params": ["sub"]
        },
        {
            "sub_idx": 1,
            "start_time": "00:15:20.00",
            "end_time": "00:20:30.00",
            "time_origin": "main",
            "video_mode": "blend",

            /*
             * If video_mode is "blend", "video_mode_params"
             * is like this:
             */
            "video_mode_params": [
                {
                    /*
                     * see https://ffmpeg.org/ffmpeg-filters.html#blend_002c-tblend
                     */
                    "blend": "all_expr='A*(if(gte(T,10),1,T/10))+B*(1-(if(gte(T,10),1,T/10)))'",

                    /*
                     * bottom layer. specify "main", or sub_idx like 1.
                     * When omitting, this script follows the previous
                     * segment.
                     */
                    "bottom_layer": "main"
                }
            ],
            "audio_mode": "amerge",
            "audio_mode_params": []
        }
    ]
}
"""

def validate_definition(definition):
    tmpl = json_loads(_sample_editinfo)
    #
    _check_type = validate_type_one_by_template
    _check_dict = validate_dict_one_by_template

    c, t = definition, tmpl
    _check_dict(c, t, t.keys(), "root")
    c, t = definition["inputs"], tmpl["inputs"]
    _check_dict(c, t, t.keys(), "'inputs'")
    c, t = definition["inputs"]["main"], tmpl["inputs"]["main"]
    _check_dict(c, t, ["file"], "'inputs[main]'")
    c, t = definition["inputs"]["sub"], tmpl["inputs"]["sub"]
    _check_type(c, t, "inputs[sub]")
    for i, c in enumerate(definition["inputs"]["sub"]):
        t = tmpl["inputs"]["sub"][0]
        _check_dict(c, t, ["file"], "'inputs[sub][%d]'" % i)
    c, t = definition["intercuts"], tmpl["intercuts"]
    _check_type(c, t, "intercuts")
    for i, c in enumerate(definition["intercuts"]):
        t = tmpl["intercuts"][0]
        _check_dict(c, t, ["sub_idx"], "'intercuts[%d]'" % i)


def _make_list_of_trims(definition):
    #
    def _translate_definition(definition):
        _inputs = definition["inputs"]  # as human readable
        _intercuts = definition["intercuts"]  # as human readable

        inputs = []  # flatten
        inputs.append(_inputs["main"])
        inputs.extend(_inputs["sub"])

        intercuts = []  # flatten, parsed time
        for i in range(len(_intercuts)):
            ins = {
                "idx": _intercuts[i]["sub_idx"] + 1,
                "start_time": parse_time(_intercuts[i].get(
                        "start_time", -1)),
                "end_time": parse_time(_intercuts[i].get("end_time", -1)),
                "time_origin": _intercuts[i].get("time_origin", "sub"),
                "video_mode": _intercuts[i].get("video_mode", "select"),
                "audio_mode": _intercuts[i].get("audio_mode", "select"),
                "video_mode_params": _intercuts[i].get(
                    "video_mode_params", []),
                "audio_mode_params": _intercuts[i].get(
                    "audio_mode_params", ["main"]),
                }
            intercuts.append(ins)

        return inputs, intercuts
    #
    def _round_time(t):
        # Round the specified "seconds" to a multiple of the
        # time width between video frames. This is to prevent
        # the difference between the trim and atrim clipping
        # width becoming bigger because the video is far coarser
        # in resolution.
        if qual["max_fps"]:
            nvframes = np.floor(t * qual["max_fps"])
            return nvframes / qual["max_fps"]
        else:
            return t
    #
    def _mk_trims_table(intercuts, einf, qual):
        # result = [
        #   [[s1, e1],...],  # for idx=0
        #   ...
        #   [[s1, e1],...],  # for idx=n
        #   ...
        # ]
        _tmp = []  # for idx=0
        for ins in intercuts:
            off = einf[ins["idx"]]["pad"] - einf[0]["pad"]
            dur = einf[ins["idx"]]["orig_duration"]
            maincounting = ins["time_origin"] == "main"
            # Let's fill in unspecified time. We must pay attention
            # to `time_origin`.
            _tmp.append([ins["start_time"], ins["end_time"]])
            if _tmp[-1][0] < 0:
                _tmp[-1][0] = off if maincounting else 0
            if _tmp[-1][1] < 0:
                _tmp[-1][1] = dur + (off if maincounting else 0)
            # Let's standardize the time reference to `main` counting.
            if ins["time_origin"] == "sub":
                _tmp[-1][0] += off
                _tmp[-1][1] += off
        # Let's make adjustments so as not to overlap. Let's give
        # priority to the material that comes later in time.
        _tmp.sort()
        result = np.array([_tmp])
        for i in range(len(_tmp) - 1):
            if result[0][i][1] > result[0][i + 1][0]:
                result[0][i][1] = result[0][i + 1][0]
        result = _round_time(result)
        for idx in range(1, len(einf)):
            off = einf[idx]["pad"] - einf[0]["pad"]
            result = np.vstack((result, [result[0] - off]))
        for idx in range(len(einf)):
            dur = einf[idx]["orig_duration"]
            result[idx][np.where(result[idx] > dur)] = dur
        return result
    #
    inputs, intercuts = _translate_definition(definition)
    files = check_and_decode_filenames(
        [inp["file"] for inp in inputs], exit_if_error=True)
    with SyncDetector() as sd:
        einf = sd.align(files)

    #
    qual = SyncDetector.summarize_stream_infos(einf)
    trims_table = _mk_trims_table(intercuts, einf, qual)
    # make a list of time ranges which will be used as trim, and atrim.
    trims_list = []
    st_main = 0
    def _desired_dur_is_too_small(s, e):
        # trim doesn't work if dur is smaller than gap between frames.
        if qual["max_fps"]:
            return (e - s) < 1./qual["max_fps"]
        else:
            return np.isclose(s, e)

    base_trims_table = _mk_trims_table(intercuts, einf, qual)
    last = 0  # default bottom layer for blend
    for i, ins in enumerate(intercuts):
        trims_list.append({
                k: ins[k] for k in (
                    "video_mode", "video_mode_params",
                    "audio_mode", "audio_mode_params")
                })
        # [[idx, start, end], ...]
        trims = []
        use_indexes = [0]
        def _get_idx(p):
            if p == "main":
                return 0
            elif p == "sub":
                return ins["idx"]
            elif isinstance(p, (int,)):
                return p + 1

        if ins["video_mode"] in ("overlay", "blend"):
            params = ins["video_mode_params"]

            # for blend, it's top layer
            use_indexes.append(ins["idx"])

            k = "bottom_layer"
            if ins["video_mode"] == "blend":
                k = "bottom_layer"
            else:
                k = "partner_layer"
            use_indexes.append(
                _get_idx(params[0].get(k, int(last) - 1)))
        else:  # select
            params = ins["video_mode_params"]
            p = params[0] if params else "sub"
            use_indexes.append(_get_idx(p))
        astart_of_use_indexes = len(use_indexes)
        if ins["audio_mode"] in ("amerge", "amix"):
            if not ins["audio_mode_params"]:
                use_indexes.extend([0, ins["idx"]])
            else:
                for p in ins["audio_mode_params"]:
                    use_indexes.append(_get_idx(p))
        else:  # select
            params = ins["audio_mode_params"]
            p = params[0] if params else "sub"
            use_indexes.append(_get_idx(p))
        for idx in use_indexes:
            trims.append((
                    idx,
                    base_trims_table[idx][i][0],
                    base_trims_table[idx][i][1]))
        trims = np.array(trims)
        if trims[:,1].min() < 0:
            trims[:,1] -= trims[:,1].min()
        trims[:,2] = trims[:,1] + (trims[:,2] - trims[:,1]).min()
        if not _desired_dur_is_too_small(st_main, trims[0,1]):
            # insert main into gap
            trims_list[-1]["main"] = (0, st_main, trims[0,1])
            last = 0
        #
        if not _desired_dur_is_too_small(trims[0,1], trims[0,2]):
            res = {"videos": [], "audios": []}
            if ins["video_mode"] == "overlay":
                p = ins["video_mode_params"][0]
                ovl_mode = p["mode"]
                ovl_cropping = p["cropping"]
                ovl_overlay = p["overlay"]
                if ovl_mode == "sub_top":
                    res["videos"].append(trims[2])
                    res["videos"].append(trims[1])
                else:
                    res["videos"].append(trims[1])
                    res["videos"].append(trims[2])
                last = res["videos"][-1][0]  # take bottom (base layer)
            elif ins["video_mode"] == "blend":
                res["videos"].append(trims[1])  # top layer
                last = res["videos"][-1][0]  # take top
                res["videos"].append(trims[2])  # bottom layer
            else:
                res["videos"].append(trims[1])
                last = res["videos"][-1][0] 
            for t in trims[astart_of_use_indexes:]:
                res["audios"].append(t)
            #
            trims_list[-1]["intercuts"] = res
        st_main = trims[0,2]
    if st_main < einf[0]["orig_duration"]:
        if not _desired_dur_is_too_small(
            st_main, einf[0]["orig_duration"]):
            trims_list.append({
                    "main": (0, st_main, einf[0]["orig_duration"]),
                    })

    return files, inputs, trims_list, qual


def build(definition):
    validate_definition(definition)
    files, inputs, trims_list, qual = _make_list_of_trims(
        definition)

    # make filter templates
    ftmpl = []
    for inp in inputs:
        f_v = Filter()
        f_v.add_filter("fps", fps=qual["max_fps"])
        f_v.add_filter("scale", qual["max_width"], qual["max_height"])
        f_v.add_filter(inp.get("v_extra_filter"))
        f_v.add_filter("setpts", "PTS-STARTPTS")
        f_v.add_filter("setsar", "1")
        f_a = Filter()
        f_a.add_filter("aresample", qual["max_sample_rate"])
        f_a.add_filter(inp.get("a_extra_filter"))
        f_a.add_filter("asetpts", "PTS-STARTPTS")
        ftmpl.append((f_v, f_a))
    #
    result_fg = []

    fconcat = Filter()
    def _mk_trimfilter(is_video, idx, trim_range):
        ftrim_range = ["%.3f" % r for r in trim_range]
        if is_video:
            f = deepcopy(ftmpl[int(idx)][0])
            f.iv.append("[%d:v]" % int(idx))
            f.insert_filter(
                1, "trim",
                *ftrim_range)
            f.append_outlabel_v()
        else:
            f = deepcopy(ftmpl[int(idx)][1])
            f.ia.append("[%d:a]" % int(idx))
            f.insert_filter(
                1, "atrim",
                *ftrim_range)
            f.append_outlabel_a()
        return f
    has_video = all(qual["has_video"])
    for ins in trims_list:
        if "main" in ins:
            # main before intercuts
            fmb_trim = ins["main"]
            if has_video:
                fmb_v = _mk_trimfilter(True, fmb_trim[0], fmb_trim[1:])
            fmb_a = _mk_trimfilter(False, fmb_trim[0], fmb_trim[1:])
            if has_video:
                result_fg.append(fmb_v.to_str())
            result_fg.append(fmb_a.to_str())
            if has_video:
                fconcat.iv.append(fmb_v.ov[0])
            fconcat.ia.append(fmb_a.oa[0])
        #
        if "intercuts" not in ins:
            continue

        #
        videos = ins["intercuts"]["videos"]
        fvs = []
        if has_video:
            for vid in videos:
                fvs.append(_mk_trimfilter(True, vid[0], vid[1:]))
            if ins["video_mode"] in ("overlay", "blend"):
                fovl = Filter()
                if ins["video_mode"] == "overlay":
                    p = ins["video_mode_params"][0]
                    vfilt = p["overlay"]
                    fvs[1].add_filter(p["cropping"])
                else:
                    vfilt = ins["video_mode_params"][0]["blend"]
                fovl.iv.append(fvs[0].ov[0])
                fovl.iv.append(fvs[1].ov[0])
    
                fovl.add_filter(ins["video_mode"], vfilt)
                fovl.append_outlabel_v()
                fconcat.iv.append(fovl.ov[0])
                result_fg.append(fvs[0].to_str())
                result_fg.append(fvs[1].to_str())
                result_fg.append(fovl.to_str())
            else:
                fconcat.iv.append(fvs[0].ov[0])
                result_fg.append(fvs[0].to_str())
        #
        audios = ins["intercuts"]["audios"]
        fas = []
        for aud in audios:
            fas.append(_mk_trimfilter(False, aud[0], aud[1:]))
        if ins["audio_mode"] in ("amerge", "amix"):
            for fa in fas:
                fa.add_filter("pan", "stereo|c0=c0|c1=c1")
            fam = Filter()
            for fa in fas:
                fam.ia.append(fa.oa[0])
            fam.add_filter(ins["audio_mode"], inputs=len(fas))
            fam.append_outlabel_a()
            for fa in fas:
                result_fg.append(fa.to_str())
            result_fg.append(fam.to_str())
            fconcat.ia.append(fam.oa[0])
        else:
            result_fg.append(fas[0].to_str())
            fconcat.ia.append(fas[0].oa[0])

    fconcat.add_filter(
        "concat",
        n=len(fconcat.ia),
        a="1", v="1" if has_video else "0")
    if has_video:
        fconcat.append_outlabel_v()
    fconcat.append_outlabel_a()
    result_fg.append(fconcat.to_str())
    if has_video:
        return files, ";\n".join(result_fg), [fconcat.ov[0]], [fconcat.oa[0]]
    else:
        return files, ";\n".join(result_fg), [], [fconcat.oa[0]]


def main(args=sys.argv):
    import argparse, textwrap

    parser = argparse.ArgumentParser(description=textwrap.dedent("""\
What this script does is quite similar to `concat_videos_by_sound_track`,
but it does a bit more general tasks. Suppose there is a main unedited
movie, there are multiple sub movie materials you want to insert into it.
With this script, these materials can be superimposed or replaced at specific
times. Unlike video editing software with a higher GUI, WYSWYG editing is
not possible and there are no effect functions, but by using this script
it is easy to insert material without being aware of synchronization point.

This script takes simple text (JSON) file describing the definition for
indicating the intercuts position like this:
--------------------------------------------------
%s
--------------------------------------------------
In `inputs`, describe the file information about the main and sub and
the filter (if necessary) to be applied to each.

In `intercuts`, describe a list of the sub material intercuts.

For `start_time` and `end_time`, you can specify either `main` counting
or sub-material counting. In the former case, set `main` as `time_origin`
and `sub` if it is the latter. In either case, it is the responsibility
of this script to determine the proper intercuts position based on the
synchronization of the audio. `video_mode` and` audio_mode` indicate
the intercuts method, and you can choose whether to replace or overlay
with sub materials in that time zone.

The "main" material will be used in the gap part where the "intercuts"
material is not inserted, however, we do not provide a mode for "main"
material. If this becomes a problem, it is good to put duplicate the media
used as the "main" material into the "sub" element. Perhaps you would like
to use "amerge" even in the gap part. In this case, you will have to
ensure that gaps are not inserted automatically and that all time zones
are filled with only "intercuts".

Although it is possible to handle audio only media, this may not be what
you expect. If any one of "main" and "sub" is included without a video
stream, even if any one of the video streams is included, the video
streams are not used. This is to avoid making the interface of the
program unintelligible. For example, if "main" does not contain a video
stream, consider making an instruction to use "main" with "select".
In this case, what should I do? Do I fill in with black images? Technically
this is not impossible at all, but I would like to avoid confusing users
who are only interested in the most basic use cases.
""" % _sample_editinfo), formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("definition",
                        help="\
Text (JSON) file describing the definition for indicating the intercuts \
position.")
    parser.add_argument(
        "-o", "--outfile", dest="outfile", default="compiled.mp4",
        help="Specifying the output file. (default: %(default)s)")
    parser.add_argument(
        '--mode', choices=['script_bash', 'direct'], default='script_bash',
        help="""\
Switching whether to produce bash shellscript or to call ffmpeg directly. (default: %(default)s)""")
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
    args = parser.parse_args(args[1:])
    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stderr,
        format="%(created)f|%(levelname)5s:%(module)s#%(funcName)s:%(message)s")

    files, fc, vmap, amap = build(json_load(args.definition))
    v_extra_ffargs = json_loads(args.v_extra_ffargs) if vmap else []
    a_extra_ffargs = json_loads(args.a_extra_ffargs) if amap else []
    call_ffmpeg_with_filtercomplex(
        args.mode,
        files,
        fc,
        v_extra_ffargs + a_extra_ffargs,
        zip(vmap, amap) if vmap else [amap],
        [args.outfile])


#
if __name__ == '__main__':
    main()
