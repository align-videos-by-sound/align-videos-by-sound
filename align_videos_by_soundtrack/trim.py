#! /bin/env python
# -*- coding: utf-8 -*-
"""
This module is intended as an example of one application of
"align_videos_by_soundtrack.align". This script simply trim
medias.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import sys

from align_videos_by_soundtrack.align import SyncDetector
from align_videos_by_soundtrack.communicate import (
    check_call, duration_to_hhmmss)


def main(args=sys.argv):
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "files", nargs="*",
        help="The media files which contain at least audio stream.")
    parser.add_argument(
        "-o", "--outdir", default="_dest")
    parser.add_argument(
        "--trim_end", action="store_true")
    parser.add_argument(
        '--max_misalignment', type=int, default=2*60,
        help="""\
See the help of alignment_info_by_sound_track.""")
    args = parser.parse_args(args[1:])

    import os
    if not os.path.exists(args.outdir):
        os.mkdir(args.outdir)
    with SyncDetector() as sd:
        infos = sd.align(args.files, max_misalignment=args.max_misalignment)

        for fn, editinfo in infos:
            start_offset = editinfo["trim"]
            duration = editinfo["orig_duration"] - start_offset - editinfo["trim_post"]
            if start_offset > 0 or duration > 0:
                cmd = ["ffmpeg", "-y"]
                cmd.extend(["-i", fn])
                if start_offset > 0:
                    cmd.extend(["-ss", duration_to_hhmmss(start_offset)])
                if args.trim_end and duration > 0:
                    cmd.extend(["-t", "%.3f" % duration])
                #cmd.extend(["-c:v", "copy"])
                #cmd.extend(["-c:a", "copy"])
                cmd.append(os.path.join(args.outdir, os.path.basename(fn)))
                check_call(cmd)
