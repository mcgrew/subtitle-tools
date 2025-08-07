
import os
import sys
import pyocr
from collections import defaultdict
from glob import glob
from PIL import Image

import ffmpeg
from subtitles import Subtitles, SubtitleEntry

FRAME_RATE = 10


def getenv(name, default=None):
    val = os.getenv(name)
    if val:
        val = val.lower()
        try:
            val = int(val)
        except ValueError:
            pass
    return val


def _fix_text(text):
    return (text.strip()
            .replace('| ', 'I ')
            .replace('/ ', 'I ')
            )


def text_color(image: Image, x1: int, y1: int, x2: int, y2: int):
    def flatten(c: int): return (c & 0xf0) | (c >> 4)
    cropped = image.crop((x1, y1, x2, y2))
    (_, r), (_, g), (_, b) = cropped.getextrema()
    return (flatten(r), flatten(g), flatten(b))


def postprocess(subs: Subtitles):
    def format_color(c: tuple[int]): return f'{c[2]:02X}{c[1]:02X}{c[0]:02X}'
    styles = defaultdict(int)
    for entry in subs.entries:
        if isinstance(entry, SubtitleEntry):
            styles[entry.size, entry.color] += 1

    for i, (size, color) in enumerate(styles.keys()):
        subs.style(f'Style{i}', 'MS Gothic', fontsize=size,
                   primarycolour=color, secondarycolour=color)
        for entry in subs.entries:
            if isinstance(entry, SubtitleEntry):
                print(size, color, entry.size, entry.color)
                if (entry.size == size and
                        entry.color == color):
                    entry.style = f'Style{i}'


def read_subtitles(infile, stream):
    skip_cleanup = getenv('SUBCONVERT_SKIP_CLEANUP')
    tool = pyocr.get_available_tools()[0]
#      lang = tool.get_available_languages()[0]

    width = stream['width']
    height = stream['height']
    st_index = stream['index']

    if os.path.exists('work'):
        sys.stderr.write('Work directory already present, '
                         'skipping export...\n')
    else:
        os.mkdir('work')
        sys.stderr.write('Exporting subpicture subtitles...\n')

        ff = ffmpeg.Ffmpeg('work/%06d.png').skip('audio')
        ff.filter_complex(f"[1:v][0:{st_index}]overlay,mpdecimate[out]")
        ff.input(infile, None)
        ff.input(f"color=size={width}x{height}:rate={FRAME_RATE}:color=black",
                 None).format('lavfi')
        ff.map('[out]')
        ff.time_range(0, 22 * 60)
        ff.extra_args('-vsync', 'vfr', '-frame_pts', '1')
        ff.run()

    sys.stderr.write('Performing OCR...\n')

    images = sorted(glob('work/*.png'))

    subs = Subtitles(width, height)

    for i, image in enumerate(images):
        sys.stderr.write(f'{int((i + 1) / len(images) * 100):3d}%\r')
        sys.stderr.flush()
        img = Image.open(image)
#          img.convert('L')
        builder = pyocr.builders.LineBoxBuilder()
        builder.tesseract_flags.extend(['--oem', '1'])
        lineboxes = tool.image_to_string(img, lang='eng', builder=builder)
        start_time = int(image[-10:-4]) / FRAME_RATE
        if len(images) <= i+1:
            end_time = start_time + 5
        else:
            end_time = int(images[i+1][-10:-4]) / FRAME_RATE
#          content = ''
        for linebox in lineboxes:
            ((x1, y1), (x2, y2)) = linebox.position
            r, g, b = text_color(img, x1, y1, x2, y2)
#              content += f' {linebox.content}'
#          if content:
#              subs.entry(_fix_text(content), start_time, end_time)
            subs.comment(f'{x1}, {x2}, {y1}, {y2}, '
                         f'color: {b:02X}{g:02X}{r:02X}')
            reduce_margin = min(x1, width - x2)
            x1 -= reduce_margin
            x2 += reduce_margin
            subs.entry(
                    SubtitleEntry(
                        _fix_text(linebox.content), start_time, end_time,
                        marginl=x1, marginr=width - x2, marginv=height - y2,
                        size=int((y2 - y1) / 0.75), color=(r, g, b)))
        if not skip_cleanup:
            os.remove(image)
    if skip_cleanup:
        sys.stderr.write('Skipping cleanup..\n')
    else:
        os.rmdir('work')
    sys.stderr.write('OCR Complete. Please check the output for accuracy.\n')
    postprocess(subs)
    return subs

# ffmpeg -i video.mkv
#  -f lavfi -i "color=size=1920x1080:rate=10:color=black"
#  -filter_complex "[1:v][0:s]overlay,mpdecimate[out]"
#  -map "[out]"
#  -an
#  -vsync vfr
#  -frame_pts true ocrtest/frames_%06d.png
