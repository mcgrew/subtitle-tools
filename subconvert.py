#!/usr/bin/env python3

import pyocr
from PIL import Image
from glob import glob


class SubtitleEntry:
    def __init__(self, index, text, start, end, position=(0,0,0,0)):
        self.index = index
        self.text = text.replace('| ', 'I ')
        self.start = start
        self.end = end
        self.position = position

    def _ts(self, sec:float):
        ms = int((sec % 1) * 1000)
        sec = int(sec)
        return f"{int(sec / 3600):02d}:{int(sec / 60 % 60):02d}:{sec % 60:02d},{ms:03d}"

    def __eq__(self, subtitle_entry):
        return self.text == subtitle_entry.text

    def __str__(self):
        if self.end < 0:
            return ''
        if self.start < 0:
            self.start = 0
        position = ''
#          if any(self.position)
#              position = ' X1:{0} X2:{1} Y1:{2} Y2:{3}'.format(self.position)
        return f'{self.index}\n{self._ts(self.start)} --> {self._ts(self.end)}{position}\n{self.text}\n\n'

# ffmpeg -i reincarnated_as_a_sword/S01E01.mkv -f lavfi -i "color=size=1920x1080:rate=10:color=black" -filter_complex "[1:v][0:s]overlay,mpdecimate[out]" -map "[out]" -an -vsync vfr -frame_pts true ocrtest/frames_%06d.png

tool = pyocr.get_available_tools()[0]
lang = tool.get_available_languages()[0]

images = glob('*.png')

entries = []
with open('S01E01.srt', 'w') as outfile:

    index = 0
    for i, image in enumerate(images):
        lineboxes = tool.image_to_string(Image.open(image), lang='eng', builder=pyocr.builders.LineBoxBuilder())
        start_time = int(image[7:-4]) / 10
        if len(images) <= i+1:
            end_time = start_time + 5
        else:
            end_time = int(images[i+1][7:-4]) / 10
        for linebox in lineboxes:
            ((x1, y1),(x2, y2)) = linebox.position
            index += 1
            entry = SubtitleEntry(index, linebox.content, start_time, end_time, (x1, y1, x2, y2))
            outfile.write(str(entry))

            print(entry, end='')
