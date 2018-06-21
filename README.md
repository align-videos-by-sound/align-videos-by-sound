# Align videos/sound files timewise with help of their soundtracks

This script based on alignment_by_row_channels.py by Allison Deal, see
https://github.com/allisonnicoledeal/VideoSync/blob/master/alignment_by_row_channels.py

This program reports the offset difference for audio and video files,
containing audio recordings from the same event. It relies on ffmpeg being
installed and the python libraries scipy and numpy.

New contributions have been made by Hiroaki Itoh https://github.com/hhsprings with regards to multi file support, clean up and optimizations.


Usage:

    align-videos-by-sound <file1> <file2> …

It reports back the offset. Example:

    align-videos-by-sound good_video_shitty_audio.mp4 good_audio_shitty_video.mp4

    Result: The beginning of good_video_shitty_audio.mp4 needs to be trimmed off 11.348 seconds for files to be in sync

if the --json flag is used, output is in JSON format, which could be a basis for automatic trimming by e.g. ffmpeg. Example JSON output:

    {
        "edit_list": [
            [
                "/home/jorgen/workspace/multimedia/align-videos-by-sound-python3/tests/testfiles/7-secs-in.mp4",
                -0.0
            ],
            [
                "/home/jorgen/workspace/multimedia/align-videos-by-sound-python3/tests/testfiles/3-secs-in.mp4",
                4.010666666666666
            ],
            [
                "/home/jorgen/workspace/multimedia/align-videos-by-sound-python3/tests/testfiles/full.mp4",
                6.997333333333334
            ]
        ]
    }


The script can handle more than two files