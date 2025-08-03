
import os
import sys
import pyocr
from glob import glob
from PIL import Image

import ffmpeg
import subtitles

FRAME_RATE = 10


def _fix_text(text):
    return (text.strip()
            .replace('| ', 'I ')
            .replace('/ ', 'I ')
            )


def read_subtitles(infile, stream):
    tool = pyocr.get_available_tools()[0]
#      lang = tool.get_available_languages()[0]

    width = stream['width']
    height = stream['height']
    st_index = stream['index']

    ff = ffmpeg.Ffmpeg('work/%06d.png').skip('audio')
    ff.filter_complex(f"[1:v][0:{st_index}]overlay,mpdecimate[out]")
    ff.input(infile, None)
    ff.input(f"color=size={width}x{height}:rate={FRAME_RATE}:color=black",
             None).format('lavfi')
    ff.map('[out]')
    ff.time_range(0, 23 * 60)
    ff.extra_args('-vsync', 'vfr', '-frame_pts', '1')

    if not os.path.exists('work'):
        os.mkdir('work')
    sys.stderr.write('Exporting subpicture subtitles...\n')
    ff.run()
    sys.stderr.write('Performing OCR...\n')

    images = sorted(glob('work/*.png'))

    subs = subtitles.Subtitles(width, height)

    for i, image in enumerate(images):
        sys.stderr.write(f'{int((i + 1) / len(images) * 100):3d}%\r')
        sys.stderr.flush()
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
            content += f' {linebox.content}'
        if content:
            subs.entry(_fix_text(content), start_time, end_time)
        os.remove(image)
    os.rmdir('work')
    sys.stderr.write('OCR Complete. Please check the output for accuracy.\n')
    return subs

# ffmpeg -i video.mkv
#  -f lavfi -i "color=size=1920x1080:rate=10:color=black"
#  -filter_complex "[1:v][0:s]overlay,mpdecimate[out]"
#  -map "[out]"
#  -an
#  -vsync vfr
#  -frame_pts true ocrtest/frames_%06d.png
