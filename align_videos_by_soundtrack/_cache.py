# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import absolute_import

import sys
import os
import hashlib
import shutil
import pickle

from . import __version__


try:
    cache_root_dir
except NameError:
    pkgroot = "align_videos_by_soundtrack"
    if sys.platform == "win32":
        cache_root_dir = os.path.join(
            os.environ["LOCALAPPDATA"],
            pkgroot, "%s" % __version__, "Cache")
    else:
        cache_root_dir = os.path.join(
            os.environ["HOME"],
            "." + pkgroot, "%s" % __version__, "Cache")


def make_cache_key(**for_cache_key):
    #
    d = dict(**for_cache_key)
    s = ",".join(["%r=%r" % (k, d[k]) for k in sorted(d.keys())])
    key = hashlib.md5(s.encode()).hexdigest()
    return key


def clean(funcname):
    cd = os.path.join(cache_root_dir, funcname)
    try:
        shutil.rmtree(cd)
    except:
        pass


def get(funcname, key):
    cd = os.path.join(cache_root_dir, funcname)
    cache_fn = os.path.join(cd, key)
    if os.path.exists(cache_fn):
        return pickle.load(open(cache_fn, "rb"))

def set(funcname, key, value):
    cd = os.path.join(cache_root_dir, funcname)
    if not os.path.exists(cd):
        os.makedirs(cd)
    cache_fn = os.path.join(cd, key)
    pickle.dump(value, open(cache_fn, "wb"), protocol=-1)
