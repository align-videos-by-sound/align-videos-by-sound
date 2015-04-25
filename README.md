# Align videos/sound files timewise with help of their soundtracks

This script based on alignment_by_row_channels.py by Allison Deal, see
https://github.com/allisonnicoledeal/VideoSync/blob/master/alignment_by_row_channels.py

This program reports the offset difference for audio and video files,
containing audio recordings from the same event. It relies on avconv being
installed and the python libraries scipy and numpy.


Usage:

    align-videos-by-sound <file1> <file2>

It reports back the offset. Example:

    align-videos-by-sound good_video_shitty_audio.mp4 good_audio_shitty_video.mp4

    Result: The beginning of good_video_shitty_audio.mp4 needs to be cropped 11.348 seconds for files to be in sync
