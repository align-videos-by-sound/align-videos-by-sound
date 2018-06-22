# Start of tests, should be put into python of course
# This script assumes the python interpreter is one level up in bin/python,
# as would be the case with a virtualenv build
# run this script from the command line on unixish systems with e.g
# source test-with-virtual-env.sh

../bin/python ../align_videos_by_sound_track.py --json testfiles/7-secs-in.mp4  testfiles/3-secs-in.mp4 testfiles/full.mp4
