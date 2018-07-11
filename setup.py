#! /usr/bin/env python
from __future__ import with_statement

import os.path

try:
    from setuptools import setup
except ImportError:
    # TODO: Decide whether to force "setuptools" or even to users
    #       with "distutils" only.
    from distutils.core import setup
    extra = {'scripts': [
            "bin/alignment_info_by_sound_track",
            "bin/simple_stack_videos_by_sound_track",
            ]}
else:
    extra = {
        #'test_suite': 'align_videos_by_sound_track.test',
        'entry_points': {
            'console_scripts': [
                'alignment_info_by_sound_track = align_videos_by_soundtrack.align:main',
                'concat_videos_by_sound_track = align_videos_by_soundtrack.concat:main',
                'simple_stack_videos_by_sound_track = align_videos_by_soundtrack.simple_stack_videos:main',
                'trim_by_sound_track = align_videos_by_soundtrack.trim:main',
                'simple_compile_videos_by_sound_track = align_videos_by_soundtrack.simple_compile_videos:main',
                ],
        },
    }


def get_version(fname=os.path.join('align_videos_by_soundtrack', '__init__.py')):
    with open(fname) as f:
        for line in f:
            if line.startswith('__version__'):
                return eval(line.split('=')[-1])


def get_long_description():
    descr = []
    for fname in ('README.md',):  # for PyPI, actually rst is suitable rather than markdown.
        with open(fname) as f:
            descr.append(f.read())
    return '\n\n'.join(descr)


setup(
    name="align_videos_by_sound_track",
    #license="MIT",    # choose as you like
    version=get_version(),
    description="Align videos/sound files timewise with help of their soundtracks",
    long_description=get_long_description(),
    author="Jorgen Modin",
    author_email="jorgen@webworks.se",
    url="https://github.com/jeorgen/align-videos-by-sound/",
    packages=[
        "align_videos_by_soundtrack",
        ],
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*',
    classifiers=[
        "Development Status :: 1 - Planning",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        #"License :: OSI Approved :: MIT License",  # choose as you like
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "Topic :: Utilities",
    ],
    **extra)
