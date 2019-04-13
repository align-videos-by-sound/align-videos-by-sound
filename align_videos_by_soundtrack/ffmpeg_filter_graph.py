#! /bin/env python
# -*- coding: utf-8 -*-
"""
This module includes a helper for constructing the filter graph of ffmpeg.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

from itertools import chain
from collections import defaultdict
import logging
import numpy as np  # for base_repr

__all__ = [
    "mk_single_filter_body",
    "Filter",
    "ConcatWithGapFilterGraphBuilder",
    ]

_logger = logging.getLogger(__name__)


_filter_defaults = {
    "color": {
        "c": "black",
        },
    "sine": {
        "frequency": "0",
        },
    }


def mk_single_filter_body(name, *args, **kwargs):
    r"""
    >>> print(mk_single_filter_body("color", s="960x540", d="123.45"))
    color=c=black:d=123.45:s=960x540
    >>> print(mk_single_filter_body("scale", "600", "400"))
    scale=600:400
    >>> print(mk_single_filter_body("scale", 600, 400))
    scale=600:400
    >>> print(mk_single_filter_body("concat"))
    concat
    """
    paras = _filter_defaults.get(name, {})
    paras.update(**kwargs)

    all_args = list(map(lambda a: "%s" % a, args))  # positional
    all_args += [
        "{}={}".format(k, paras[k])
        for k in sorted(paras.keys())]

    return "{}{}{}".format(
        name,
        "=" if all_args else "",
        ":".join(all_args))


_olab_counter = defaultdict(int)


class Filter(object):
    """
    >>> f = Filter()
    >>> f.iv.append("[0:v]")
    >>> f.add_filter("scale", "600", "400")
    >>> f.add_filter("setsar", "1")
    >>> f.ov.append("[v0]")
    >>> print(f.to_str())
    [0:v]scale=600:400,setsar=1[v0]
    >>> #
    >>> f = Filter()
    >>> f.iv.append("[0:v]")
    >>> f.iv.append("[1:v]")
    >>> f.add_filter("concat")
    >>> f.ov.append("[vc0]")
    >>> print(f.to_str())
    [0:v][1:v]concat[vc0]
    >>> #
    >>> f = Filter()
    >>> f.iv.append("[0:v]")
    >>> f.iv.append("[1:v]")
    >>> f.add_filter("concat")
    >>> f.append_outlabel_v()
    >>> print(f.to_str())
    [0:v][1:v]concat[v1]
    >>> #
    >>> f = Filter()
    >>> f.ia.append("[0:a]")
    >>> f.ia.append("[1:a]")
    >>> f.add_filter("concat")
    >>> f.append_outlabel_a()
    >>> print(f.to_str())
    [0:a][1:a]concat[a1]
    """
    def __init__(self):
        self.iv = []  # the labels of input video streams
        self.ia = []  # the labels of input audio streams
        self._filters = []
        self.ov = []  # the labels of output video streams
        self.oa = []  # the labels of output audio streams

    def _labels_to_str(self, v, a):
        if not v and a:
            v = [""] * len(a)
        if not a and v:
            a = [""] * len(v)
        return "".join(chain.from_iterable(zip(v, a)))
        
    def add_filter(self, name, *args, **kwargs):
        if name:
            self._filters.append(
                mk_single_filter_body(name, *args, **kwargs))

    def insert_filter(self, i, name, *args, **kwargs):
        if name:
            self._filters.insert(
                i, mk_single_filter_body(name, *args, **kwargs))

    def append_outlabel_v(self, templ="[v%(counter)s]"):
        global _olab_counter
        _olab_counter[templ] += 1
        self.ov.append(templ % dict(
                counter=np.base_repr(_olab_counter[templ], 36)))

    def append_outlabel_a(self, templ="[a%(counter)s]"):
        global _olab_counter
        _olab_counter[templ] += 1
        self.oa.append(templ % dict(
                counter=np.base_repr(_olab_counter[templ], 36)))

    def to_str(self):
        ilabs = self._labels_to_str(self.iv, self.ia)
        filterbody = ",".join(self._filters)
        olabs = self._labels_to_str(self.ov, self.oa)
        return ilabs + filterbody + olabs


class ConcatWithGapFilterGraphBuilder(object):
    def __init__(self, ident, w=960, h=540, fps=29.97, sample_rate=44100):
        self._ident = ident

        # black video stream
        fpadv = Filter()
        fpadv.add_filter(
            "color", s="%dx%d" % (w, h), d="{duration:.3f}")
        fpadv.add_filter("fps", fps="%.2f" % fps)
        fpadv.add_filter("setsar", "1")
        fpadv.ov.append("[gap{gapno}v%s]" % ident)
        self._tmpl_gapv = (fpadv.to_str(), "".join(fpadv.ov))

        # aevalsrc
        nch = 2
        fpada = Filter()
        fpada.add_filter(
            "aevalsrc",
            exprs="'%s'" % ("|".join(["0"] * nch)),
            sample_rate="%d" % sample_rate,
            d="{duration:.3f}")
        fpada.oa.append("[gap{{gapno}}a{ident}]".format(ident=ident))
        self._tmpl_gapa = (
            fpada.to_str(), "".join(fpada.oa))

        # filter to original video stream
        fbodyv = Filter()
        fbodyv.iv.append("[{stream_no}:v]")
        fbodyv.add_filter("fps", fps="%.2f" % fps)
        fbodyv.add_filter("{v_filter_extra}scale", w, h)
        fbodyv.add_filter("setsar", "1")
        fbodyv.ov.append("[v%s_{bodyident}]" % ident)
        self._bodyv = (fbodyv.to_str(), "".join(fbodyv.ov))

        # filter to original audio stream
        fbodya = Filter()
        fbodya.ia.append("[{stream_no}:a]")
        fbodya.add_filter(
            "{a_filter_extra}aresample", sample_rate)
        fbodya.oa.append("[a%s_{bodyident}]" % ident)
        self._bodya = (fbodya.to_str(), "".join(fbodya.oa))

        #
        self._result = []
        self._fconcat = Filter()
        self._gapno = 0
        self._numbody = 0

    def add_video_gap(self, duration):
        if duration <= 0:
            return self
        self._result.append(
            self._tmpl_gapv[0].format(
                gapno=np.base_repr(self._gapno, 36), duration=duration))
        self._fconcat.iv.append(self._tmpl_gapv[1].format(
                gapno=np.base_repr(self._gapno, 36)))
        self._gapno += 1

        return self

    def add_audio_gap(self, duration):
        if duration <= 0:
            return self
        self._result.append(
            self._tmpl_gapa[0].format(
                gapno=np.base_repr(self._gapno, 36), duration=duration))
        self._fconcat.ia.append(self._tmpl_gapa[1].format(
                gapno=np.base_repr(self._gapno, 36)))
        self._gapno += 1

        return self

    def add_video_content(self, stream_no, v_filter_extra):
        self._result.append(
            self._bodyv[0].format(
                stream_no=stream_no,
                bodyident=np.base_repr(self._numbody, 36),
                v_filter_extra=v_filter_extra + "," if v_filter_extra else ""))
        self._fconcat.iv.append(self._bodyv[1].format(
                bodyident=np.base_repr(self._numbody, 36)))
        self._numbody += 1

        return self

    def add_audio_content(self, stream_no, a_filter_extra):
        self._result.append(
            self._bodya[0].format(
                stream_no=stream_no,
                bodyident=np.base_repr(self._numbody, 36),
                a_filter_extra=a_filter_extra + "," if a_filter_extra else ""))
        self._fconcat.ia.append(self._bodya[1].format(
                bodyident=np.base_repr(self._numbody, 36)))
        self._numbody += 1

        return self

    def build(self):
        niv = len(self._fconcat.iv)
        nia = len(self._fconcat.ia)
        if max(niv, nia) <= 1:
            # we can't concat only one stream!
            raise Exception("You haven't prepared to call this method.")
        self._fconcat.add_filter(
            "concat",
            n=max(niv, nia),
            v="1" if niv > 1 else "0",
            a="1" if nia > 1 else "0")
        if niv > 1:
            self._fconcat.ov.append("[vc%s]" % self._ident)
        if nia > 1:
            self._fconcat.oa.append("[ac%s]" % self._ident)
        self._result.append(self._fconcat.to_str())
        #
        return (
            ";\n".join(self._result),
            self._fconcat.ov[-1] if self._fconcat.ov else "",
            self._fconcat.oa[-1] if self._fconcat.oa else "")


#
if __name__ == '__main__':
    import doctest
    doctest.testmod()
