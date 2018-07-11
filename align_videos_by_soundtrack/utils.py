# -*- coding: utf-8 -*-
#
"""
This module contains tiny extra helpers.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import sys
import os
import io
import json
import logging


__all__ = [
    "check_and_decode_filenames",
    "json_load",
    "json_loads",
    ]

_logger = logging.getLogger(__name__)


if hasattr("", "decode"):  # python 2
    def _decode(s):
        if isinstance(s, (str,)):  # bytes in python 2
            return s.decode(sys.stdout.encoding)
        return s
else:
    def _decode(s):
        return s


def check_and_decode_filenames(
    files,
    min_num_files=0,
    exit_if_error=False):

    result = list(map(_decode, map(os.path.abspath, files)))
    nf_files = [path for path in result if not os.path.isfile(path)]
    if nf_files:
        for nf in nf_files:
            _logger.error("{}: No such file.".format(nf))
        if exit_if_error:
            sys.exit(1)
        return []
    if min_num_files and len(result) < min_num_files:
        _logger.error(
            "At least {} files are necessary.".format(
                min_num_files))
        if exit_if_error:
            sys.exit(1)
        return []

    return result


# ================================================================
#
# Configuration related
#

def json_loads(jsonsting):
    import re
    _pat = re.compile(
        r'''/\*.*?\*/|"(?:\\.|[^\\"])*"''',
        re.DOTALL | re.MULTILINE)
    def _repl(m):
        s = m.group(0)
        if s.startswith("/"):
            return " "
        else:
            return s
    return json.loads(re.sub(_pat, _repl, jsonsting))


def json_load(jsonfilename):
    raw = io.open(jsonfilename, encoding="utf-8").read()
    return json_loads(raw)


# ---------------------------------------
#
# Validation helpers
#
def validate_type_one_by_template(
    chktrg, tmpl, depthstr, not_empty=True, exit_on_error=True):

    if type(chktrg) != type(tmpl) or not chktrg:
        _logger.error("""%s must be %s""" % (
                depthstr, type(tmpl)))
        if exit_on_error:
            sys.exit(1)
        return False
    return True


def validate_dict_one_by_template(
    chktrg, tmpl, mandkeys, depthstr, not_empty=True, exit_on_error=True):

    if not validate_type_one_by_template(
        chktrg, tmpl, depthstr, not_empty, exit_on_error):
        return False

    for mk in mandkeys:
        if mk not in chktrg:
            _logger.error("""Missing key '%s' in %s""" % (
                    mk, depthstr))
            if exit_on_error:
                sys.exit(1)
            return False
    allow_keys = tmpl.keys()
    unk = (set(allow_keys) | set(chktrg.keys())) - set(allow_keys)
    if unk:
        _logger.error("""Unknown keys in %s: %s""" % (
                depthstr, ", ".join(list(unk))))
        if exit_on_error:
            sys.exit(1)
        return False
    return True


if __name__ == '__main__':
    import doctest
    doctest.testmod()
