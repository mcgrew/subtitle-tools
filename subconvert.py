#!/usr/bin/env python3

import pyocr
import os
import sys
import json
from argparse import ArgumentParser
from PIL import Image
from glob import glob

import ffmpeg
import subtitles

FRAME_RATE = 4


# ffmpeg -i video.mkv
#  -f lavfi -i "color=size=1920x1080:rate=10:color=black"
#  -filter_complex "[1:v][0:s]overlay,mpdecimate[out]"
#  -map "[out]"
#  -an
#  -vsync vfr
#  -frame_pts true ocrtest/frames_%06d.png


def main(args):

    tool = pyocr.get_available_tools()[0]
#      lang = tool.get_available_languages()[0]

    ff = ffmpeg.Ffmpeg('work/%06d.png').skip('audio')
    ff.filter_complex("[1:v][0:s]overlay,mpdecimate[out]")
    ff.input('video.mkv', None)
    ff.input(f"color=size=720x480:rate={FRAME_RATE}:color=black", None).format('lavfi')
    ff.map('[out]')
    ff.time_range(0, 23 * 60)
    ff.extra_args('-vsync', 'vfr', '-frame_pts', '1')

    if not os.path.exists('work'):
        os.mkdir('work')
    print('Exporting subtitles...')
    ff.run()
    print('Reading Subtitles...')

    images = sorted(glob('work/*.png'))

    with open('video.ass', 'w') as outfile:

        subs = subtitles.Subtitles()
        subs.style('Default', 'MS Gothic', fontsize=36, marginv = 40)

        for i, image in enumerate(images):
            sys.stdout.write(f'{int((i + 1) / len(images) * 100):3d}%\r')
            sys.stdout.flush()
            img = Image.open(image)
            img.convert('L')
            builder = pyocr.builders.LineBoxBuilder()
            builder.tesseract_flags.extend(['--oem', '1'])
            lineboxes = tool.image_to_string(img, lang='eng', builder=builder)
            start_time = int(image[-10:-4]) / FRAME_RATE
            if len(images) <= i+1:
                end_time = start_time + 5
            else:
                end_time = int(images[i+1][-10:-4]) / FRAME_RATE
            content = ''
            for linebox in lineboxes:
                ((x1, y1), (x2, y2)) = linebox.position
                content += f'{linebox.content}\n'
            if content:
                subs.entry(content, start_time, end_time)
            os.remove(image)
        outfile.write(subs.ssa())
    os.rmdir('work')

main(None)
