# Align videos/sound files timewise with help of their soundtracks

This package based on alignment_by_row_channels.py by Allison Deal, see
https://github.com/allisonnicoledeal/VideoSync/blob/master/alignment_by_row_channels.py

## Installation
```
cd align-videos-by-sound
python setup.py install
```

After that, you can use this package as python module, or some sample application scripts (`alignment_info_by_sound_track`, `simple_stack_videos_by_sound_track`, etc).

## Scripts:
### alignment_info_by_sound_track
This program reports the offset difference for audio and video files,
containing audio recordings from the same event (news event, concert event, theatre play or something else). It relies on ffmpeg being installed and the python libraries scipy and numpy.

Usage:

    align_videos_by_soundtrack <file1> <file2> [<file3>…]

It reports back the offset. Example:

    align_videos_by_soundtrack good_video_shitty_audio.mp4 good_audio_shitty_video.mp4

    Result: The beginning of good_video_shitty_audio.mp4 needs to be trimmed off 11.348 seconds for files to be in sync

if the --json flag is used, output is in JSON format, which could be a basis for automatic trimming by e.g. ffmpeg. Imagine you have recordings of an event. If you want to make the videos start at the same time as the _last_ started recording of the event use the "trim" value. This is good for example when all recordings have started before the event. 

If you have some recordings starting _after_ the event has started, use "pad" to pad the later starting videos to start at the same time as the first started recording. 

Example JSON output:

    {
        "edit_list": [
            [
                "/home/jorgen/workspace/multimedia/align-videos-by-sound-python3/tests/testfiles/7-secs-in.mp4",
                {
                    "trim": -0.0,
                    "pad": 6.994666666666666,
                    "orig_duration": 8.08,
                    "trim_post": 0.010666666666667268,
                    "pad_post": 0.005333333333334522,
                    "orig_streams": [
                        {
                            "type": "Video",
                            "resolution": [
                                [
                                    10,
                                    18
                                ],
                                "[SAR 81:80 DAR 9:16]"
                            ],
                            "fps": 25.0
                        },
                        {
                            "type": "Audio",
                            "sample_rate": 48000
                        }
                    ]
                }
            ],
            [
                "/home/jorgen/workspace/multimedia/align-videos-by-sound-python3/tests/testfiles/3-secs-in.mp4",
                {
                    "trim": 4.010666666666666,
                    "pad": 2.984,
                    "orig_duration": 12.08,
                    "trim_post": 0.0,
                    "pad_post": 0.016000000000000014,
                    "orig_streams": [
                        {
                            "type": "Video",
                            "resolution": [
                                [
                                    10,
                                    18
                                ],
                                "[SAR 81:80 DAR 9:16]"
                            ],
                            "fps": 25.0
                        },
                        {
                            "type": "Audio",
                            "sample_rate": 48000
                        }
                    ]
                }
            ],
            [
                "/home/jorgen/workspace/multimedia/align-videos-by-sound-python3/tests/testfiles/full.mp4",
                {
                    "trim": 6.994666666666666,
                    "pad": 0.0,
                    "orig_duration": 15.08,
                    "trim_post": 0.01600000000000179,
                    "pad_post": 0.0,
                    "orig_streams": [
                        {
                            "type": "Video",
                            "resolution": [
                                [
                                    10,
                                    18
                                ],
                                "[SAR 81:80 DAR 9:16]"
                            ],
                            "fps": 25.0
                        },
                        {
                            "type": "Audio",
                            "sample_rate": 48000
                        }
                    ]
                }
            ]
        ]
    }




Please note that this package does not include functionality to do the actual editing for trimming/padding yet.

The script can handle more than two files

### simple_stack_videos_by_sound_track
This script basically merges the given videos by `hstack`, and `vstack`.

Usage:

    simple_stack_videos_by_sound_track <file1> <file2> [<file3>…]

See `simple_stack_videos_by_sound_track --help` for more details.


### concat_videos_by_sound_track
Regarding an event such as a certain concert, suppose that there is unedited media
that shoots and records the whole, and on the other hand, there are multiple divided
media such as stop recording halfway.

This script combines the latter with filling the gap, based on the former sound tracks.

Usage:

    concat_videos_by_sound_track <base> <divided1> <divided2> [<divided3>…]

Audio-only media may be passed to both `base` and `divided`.

See `concat_videos_by_sound_track --help` for more details.


### simple_compile_videos_by_sound_track
What this script does is quite similar to `concat_videos_by_sound_track`, but it does
a bit more general tasks. Suppose there is a main unedited movie, there are multiple
sub movie materials you want to insert into it. With this script, these materials can
be superimposed or replaced at specific times. Unlike video editing software with a
higher GUI, WYSWYG editing is not possible and there are no effect functions, but
by using this script it is easy to insert material without being aware of synchronization
point.

Usage:

    simple_compile_videos_by_sound_track edit_definitionfile

See `simple_compile_videos_by_sound_track --help` for more details.

### simple_html5_simult_player_builder_by_sound_track
This script creates a simultaneous playing player using the video (or audio) elements
of html 5.

It is similar to "simple_stack_videos_by_sound_track", but since it does not involve media
editing, it will be very useful if you want to know the result quickly.

Usage:

    simple_html5_simult_player_builder_by_sound_track <file1> <file2> [<file3>…]
