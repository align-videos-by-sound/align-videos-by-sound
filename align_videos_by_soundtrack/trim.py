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
import logging

from .align import SyncDetector
from .communicate import (
    check_call,
    duration_to_hhmmss)
from .utils import check_and_decode_filenames
from . import cli_common


_logger = logging.getLogger(__name__)


def main(args=sys.argv):
    parser = cli_common.AvstArgumentParser(description="""\
Trim media based on synchronization with audio tracks.""")
    parser.add_argument(
        "files", nargs="+",
        help="The media files which contain at least audio stream.")
    parser.add_argument(
        "-o", "--outdir", default="_dest")
    parser.add_argument(
        "--trim_end", action="store_true")
    #####
    args = parser.parse_args(args[1:])
    cli_common.logger_config()

    files = check_and_decode_filenames(args.files)
    if not files:
        parser.print_usage()
        sys.exit(1)

    import os
    if not os.path.exists(args.outdir):
        os.mkdir(args.outdir)
    with SyncDetector(
        params=args.summarizer_params,
        clear_cache=args.clear_cache) as sd:
        infos = sd.align(
            files,
            known_delay_map=args.known_delay_map)

        for fn, editinfo in list(zip(files, infos)):
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
