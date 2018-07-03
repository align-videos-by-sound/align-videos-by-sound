#! /bin/env python
# -*- coding: utf-8 -*-
"""
This module includes a helper for constructing the filter graph of ffmpeg.
"""
from __future__ import unicode_literals
from __future__ import absolute_import

from itertools import chain
import logging

__all__ = [
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


def _mk_single_filter_body(name, *args, **kwargs):
    r"""
    >>> print(_mk_single_filter_body("color", s="960x540", d="123.45"))
    color=c=black:d=123.45:s=960x540
    >>> print(_mk_single_filter_body("scale", "600", "400"))
    scale=600:400
    >>> print(_mk_single_filter_body("concat"))
    concat
    """
    paras = _filter_defaults.get(name, {})
    paras.update(**kwargs)

    all_args = list(args)  # positional
    all_args += [
        "{}={}".format(k, paras[k])
        for k in sorted(paras.keys())]

    return "{}{}{}".format(
        name,
        "=" if all_args else "",
        ":".join(all_args))


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
        self._filters.append(
            _mk_single_filter_body(name, *args, **kwargs))

    def to_str(self):
        ilabs = self._labels_to_str(self.iv, self.ia)
        filterbody = ",".join(self._filters)
        olabs = self._labels_to_str(self.ov, self.oa)
        return ilabs + filterbody + olabs


class ConcatWithGapFilterGraphBuilder(object):
    def __init__(self, ident, w=960, h=540, sample_rate=44100):
        self._ident = ident

        # black video stream
        fpadv = Filter()
        fpadv.add_filter(
            "color", s="%dx%d" % (w, h), d="{duration:.3f}")
        fpadv.add_filter("setsar", "1")
        fpadv.ov.append("[gap{gapno}v%s]" % ident)
        self._tmpl_gapv = (fpadv.to_str(), "".join(fpadv.ov))

        # silence left; silence right; -> amerge
        fpada = [Filter(), Filter(), Filter()]
        nch = 2
        for i in range(nch):
            fpada[i].add_filter(
                "sine", sample_rate="%d" % sample_rate,
                d="{duration:.3f}")
            olab = "[gap{{gapno}}a_c{i}_{ident}]".format(ident=ident, i=i)
            fpada[i].oa.append(olab)
            fpada[-1].iv.append(olab)
        fpada[-1].add_filter("amerge", "%d" % len(fpada[-1].iv))
        fpada[-1].oa.append("[gap{{gapno}}a{ident}]".format(ident=ident))
        self._tmpl_gapa = (
            ";\n".join([fpada[i].to_str()
                        for i in range(len(fpada))]),
            "".join(fpada[-1].oa))

        # filter to original video stream
        fbodyv = Filter()
        fbodyv.iv.append("[{stream_no}:v]")
        fbodyv.add_filter("{v_filter_extra}scale", "%d" % w, "%d" % h)
        fbodyv.add_filter("setsar", "1")
        fbodyv.ov.append("[v%s_{bodyident}]" % ident)
        self._bodyv = (fbodyv.to_str(), "".join(fbodyv.ov))

        # filter to original audio stream
        fbodya = Filter()
        fbodya.ia.append("[{stream_no}:a]")
        fbodya.add_filter(
            "{a_filter_extra}aresample", "%d" % sample_rate)
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
            self._tmpl_gapv[0].format(gapno=self._gapno, duration=duration))
        self._fconcat.iv.append(self._tmpl_gapv[1].format(gapno=self._gapno))
        self._gapno += 1

        return self

    def add_audio_gap(self, duration):
        if duration <= 0:
            return self
        self._result.append(
            self._tmpl_gapa[0].format(gapno=self._gapno, duration=duration))
        self._fconcat.ia.append(self._tmpl_gapa[1].format(gapno=self._gapno))
        self._gapno += 1

        return self

    def add_video_content(self, stream_no, v_filter_extra):
        self._result.append(
            self._bodyv[0].format(
                stream_no=stream_no,
                bodyident=self._numbody,
                v_filter_extra=v_filter_extra + "," if v_filter_extra else ""))
        self._fconcat.iv.append(self._bodyv[1].format(bodyident=self._numbody))
        self._numbody += 1

        return self

    def add_audio_content(self, stream_no, a_filter_extra):
        self._result.append(
            self._bodya[0].format(
                stream_no=stream_no,
                bodyident=self._numbody,
                a_filter_extra=a_filter_extra + "," if a_filter_extra else ""))
        self._fconcat.ia.append(self._bodya[1].format(bodyident=self._numbody))
        self._numbody += 1

        return self

    def build(self):
        if len(self._fconcat.iv) > 1:
            self._fconcat.add_filter(
                "concat",
                n="%d" % len(self._fconcat.iv), v="1", a="1")
            self._fconcat.ov.append("[vc%s]" % self._ident)
            self._fconcat.oa.append("[ac%s]" % self._ident)
            self._result.append(self._fconcat.to_str())
        else:
            self._fconcat.ov.extend(self._fconcat.iv)
            self._fconcat.oa.extend(self._fconcat.ia)
        #
        return (
            ";\n".join(self._result),
            self._fconcat.ov[0],
            self._fconcat.oa[0])


#
if __name__ == '__main__':
    import doctest
    doctest.testmod()
