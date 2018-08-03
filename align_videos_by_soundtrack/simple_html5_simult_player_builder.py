#! /bin/env python
# -*- coding: utf-8 -*-
"""
This module is intended as an example of one application of
"align_videos_by_soundtrack.align".
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import os
import sys
import json
import logging

from .align import SyncDetector
from .utils import check_and_decode_filenames
from . import cli_common
from .utils import (
    check_and_decode_filenames,
    path2url,
)


_logger = logging.getLogger(__name__)


_tmpl_outer = """\
<html>
<head>
<script type="text/javascript" src="https://ajax.googleapis.com/ajax/libs/jquery/3.2.1/jquery.min.js"></script>
<script>
const delays = %(delays)s;
const base = delays.find(function (e) { return e == 0.0; });
const plyrs = [];

function play() {
    plyrs.forEach(function (p, i) { p.play(); });
}
function pause() {
    plyrs.forEach(function (p, i) { p.pause(); });
}
function sync() {
    let now = plyrs[base].currentTime;
    plyrs.forEach(function (p, i) {
            p.currentTime = now + delays[i];
        });
}
function advance(v) {
    let paused = plyrs.findIndex(function (e) { return e.paused; }) >= 0;
    pause();
    let now = plyrs[base].currentTime;
    plyrs.forEach(function (p, i) {
        p.currentTime = now + v;
    });
    sync();
    if (!paused) {
        setTimeout(play, plyrs.length * 700);
    }
}
$(document).ready(function() {
    for (i = 0; i < delays.length; ++i) {
        plyrs.push(document.getElementById("%(ident_prefix)s" + i));
    }
    sync();
});
</script>
</head>
<body>
<div>
<button onclick="advance(-15.0);">-15</button>
<button onclick="advance(-5.0);">-5</button>
<button onclick="play();">Play</button>
<button onclick="pause();">Pause</button>
<button onclick="advance(5.0);">+5</button>
<button onclick="advance(15.0);">+15</button>
</div>

%(medias_tab)s

</body>
</html>"""

_tmpl_media = {
    True: """\
<%(media_type)s id="%(ident_prefix)s%(index)d" width="%(width)d" height="%(height)d">
  <source src="%(media)s" type="%(media_detailtype)s">
</%(media_type)s>""",
    False: """\
<%(media_type)s id="%(ident_prefix)s%(index)d">
  <source src="%(media)s" type="%(media_detailtype)s">
</%(media_type)s>""",
}


_MEDIA_TYPES = {
    (".mp4", True): ("video", "video/mp4"),
    (".mp4", False): ("video", "video/mp4"),
    (".ogg", True): ("video", "video/ogg"),

    (".mp3", False): ("audio", "audio/mpeg"),
    (".ogg", False): ("audio", "audio/ogg"),
    (".wav", False): ("audio", "audio/wav"),
    # TODO: more? (WebM	video/webm, or extension variations like ".mpeg4")
    }


def build(args):
    shape = json.loads(args.shape) if args.shape else (2, 2)
    files = check_and_decode_filenames(args.files)
    with SyncDetector(
        params=args.summarizer_params,
        clear_cache=args.clear_cache) as sd:
        einf = sd.align(
            files,
            known_delay_map=args.known_delay_map)

    ident_prefix = "simltplayer"

    medias = []
    for i, inf in enumerate(einf):
        ext = os.path.splitext(args.files[i])[1].lower()
        has_video = inf["orig_streams_summary"]["num_video_streams"] > 0
        medias.append(_tmpl_media[has_video] % dict(
                media_type=_MEDIA_TYPES[(ext, has_video)][0],
                ident_prefix=ident_prefix,
                index=i,
                width=args.w,
                height=args.h,
                media=path2url(files[i]),
                media_detailtype=_MEDIA_TYPES[(ext, has_video)][1],
                ))

    medias_tab = ["<table>"]
    for i, m in enumerate(medias):
        if i % shape[0] == 0:
            if i > 0:
                medias_tab.append("</tr>")
            medias_tab.append("<tr>")
        medias_tab.append("<td>")
        medias_tab.append(m)
        medias_tab.append("</td>")
    medias_tab.append("</tr>")
    medias_tab.append("</table>")

    outer = _tmpl_outer % dict(
        ident_prefix=ident_prefix,
        delays=[float("%.3f" % inf["trim"]) for inf in einf],
        medias_tab="\n".join(medias_tab))
    return outer


def main(args=sys.argv):
    parser = cli_common.AvstArgumentParser(description="""\
Create a simultaneous playing player using the video and audio elements of html 5.""")
    parser.add_argument(
        "files", nargs="+",
        help="The media files which contains both video and audio.")
    #####
    parser.add_argument(
        '--shape', type=str, default="[2, 2]",
        help="The shape of the tile, like '[2, 2]'. (default: %(default)s)")
    parser.add_argument(
        '--width-per-cell', dest="w", type=int, default=480,
        help="Width of the cell. (default: %(default)d)")
    parser.add_argument(
        '--height-per-cell', dest="h", type=int, default=270,
        help="Height of the cell. (default: %(default)d)")
    #####
    args = parser.parse_args(args[1:])
    cli_common.logger_config()
    print(build(args))


#
if __name__ == '__main__':
    main()
