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
                    "pad": 6.997333333333334
                }
            ],
            [
                "/home/jorgen/workspace/multimedia/align-videos-by-sound-python3/tests/testfiles/3-secs-in.mp4",
                {
                    "trim": 4.010666666666666,
                    "pad": 2.9866666666666672
                }
            ],
            [
                "/home/jorgen/workspace/multimedia/align-videos-by-sound-python3/tests/testfiles/full.mp4",
                {
                    "trim": 6.997333333333334,
                    "pad": 0.0
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

Audio-only media may be passed to "base". For now, except for "base", both video stream
and audio stream must be included.

See `concat_videos_by_sound_track --help` for more details.
