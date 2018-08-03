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
    "validate_type_one_by_template",
    "validate_dict_one_by_template",
    "validate_list_of_dict_one_by_template",
    "path2url",
    ]

_logger = logging.getLogger(__name__)


if hasattr("", "decode"):  # python 2
    def _decode(s):
        if isinstance(s, (str,)):  # bytes in python 2
            return s.decode(sys.getfilesystemencoding())
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
    chktrg, tmpl, depthstr="",
    size_min=1, size_max=-1, exit_on_error=True):

    if type(chktrg) != type(tmpl):
        _logger.error("""%s must be %s""" % (
                depthstr, type(tmpl)))
        if exit_on_error:
            sys.exit(1)
        return False
    if ((size_min > 0 and len(chktrg) < size_min) or (
            size_max > 0 and len(chktrg) > size_max)):
        if size_min > 0 and size_max <= 0:
            bs = "greater equal than %d" % size_min
        elif size_min <= 0 and size_max > 0:
            bs = "less equal than %d" % size_max
        elif size_min == size_max:
            bs = "%d" % (size_min)
        else:
            bs = "between %d and %d" % (size_min, size_max)
        _logger.error("""The length of %s must be %s""" % (
                depthstr, bs))
        if exit_on_error:
            sys.exit(1)
        return False
    return True


def validate_dict_one_by_template(
    chktrg, tmpl, mandkeys=[], depthstr="", not_empty=True, exit_on_error=True):

    if not validate_type_one_by_template(
        chktrg, tmpl, depthstr,
        size_min=1 if (not_empty or mandkeys) else 0,
        exit_on_error=exit_on_error):
        return False
    depthstr = "in %s" % depthstr if depthstr else ""
    for mk in mandkeys:
        if mk not in chktrg:
            _logger.error("""Missing key '%s' %s""" % (
                    mk, depthstr))
            if exit_on_error:
                sys.exit(1)
            return False
    allow_keys = tmpl.keys()
    unk = (set(allow_keys) | set(chktrg.keys())) - set(allow_keys)
    if unk:
        _logger.error("""Unknown keys %s: %s""" % (
                depthstr, ", ".join(list(unk))))
        if exit_on_error:
            sys.exit(1)
        return False
    return True


def validate_list_of_dict_one_by_template(
    chktrg, itemdict_tmpl, itemdict_mandkeys=[], depthstr="",
    list_size_min=1, list_size_max=-1,
    itemdict_not_empty=True, exit_on_error=True):

    if not validate_type_one_by_template(
        chktrg, [itemdict_tmpl], depthstr,
        list_size_min, list_size_max, exit_on_error):
        return False

    for i, td in enumerate(chktrg):
        if not validate_dict_one_by_template(
            td, itemdict_tmpl, itemdict_mandkeys,
            depthstr + "[%d]" % i,
            itemdict_not_empty,
            exit_on_error):
            return False
    return True


try:
    import pathlib  # python 3.4+

    def path2url(path):
        return pathlib.Path(os.path.abspath(path)).as_uri()
except ImportError:
    # python 2
    # (we would not support python 3.0 ~ 3.3.)
    import urlparse
    import urllib

    def path2url(path):
        return urlparse.urljoin(
            'file:', urllib.pathname2url(os.path.abspath(path)))


if __name__ == '__main__':
    import doctest
    doctest.testmod()
