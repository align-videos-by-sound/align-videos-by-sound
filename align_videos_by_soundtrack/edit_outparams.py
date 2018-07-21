#! /usr/bin/env python
# -*- coding: utf-8 -*-
"""
This module contains only class for parameters of the editor
scripts for output.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

import logging

from . import communicate
from .utils import (
    json_loads,
    validate_dict_one_by_template)


__all__ = [
    'EditorOutputParams',
    ]

_logger = logging.getLogger(__name__)


class EditorOutputParams(object):
    """
    Parameter used by editor scripts.

    You can specify sample_rate, fps. In any case, if not specified,
    or specified less equals zero, the maximum in the input movie is used.
    Using the maximum in the input movie can cause problems with ffmpeg.
    Especially fps is. Perhaps due to memory problems, ffmpeg not only
    gave errors but I also experienced a blue screen on Windows machines.
    It may be risky to unify to the highest fps when input with various
    fps mixed.
    """
    def __init__(self, **kwargs):
        self.sample_rate = kwargs.get("sample_rate", -1)
        self.fps = kwargs.get("fps", 29.97)

    @staticmethod
    def from_json(s):
        if s:
            d = json_loads(s)

            tmpl = EditorOutputParams()
            validate_dict_one_by_template(d, tmpl.__dict__)
            return EditorOutputParams(**d)
        return EditorOutputParams()


if __name__ == "__main__":
    import doctest
    doctest.testmod()
