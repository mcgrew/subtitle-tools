
import os
import sys
import pyocr
from collections import defaultdict
from typing import Iterator
from dataclasses import dataclass
from glob import glob
from multiprocessing.pool import Pool
from PIL import Image

import ffmpeg
from subtitles import Subtitles, SubtitleEntry

FRAME_RATE = 10
WORKDIR = '/tmp/work'


@dataclass
class TextLine:
    start: float
    content: str
    size: int
    marginl: int
    marginr: int
    marginv: int
    color: tuple[int, int, int]
    end: float = 0

    def __post_init__(self):
        # fix the text to account for common errors
        self.content = (self.content.strip()
                        .replace('| ', 'I ')
                        .replace('/ ', 'I '))

    def __cmp__(self, textline):
        if self.start < textline.start:
            return -1
        if self.start > textline.start:
            return 1
        return 0


def has_descenders(text):
    descenders = set('gjpqy,')
    return bool(descenders.intersection(text))


def getenv(name, default=None):
    val = os.getenv(name)
    if val:
        val = val.lower()
        try:
            val = int(val)
        except ValueError:
            pass
    return val


def text_color(image: Image, x1: int, y1: int, x2: int, y2: int):
    cropped = image.crop((x1, y1, x2, y2))
    (_, r), (_, g), (_, b) = cropped.getextrema()
    return (r, g, b)


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


def dump_subs(infile, stream):
    width = stream['width']
    height = stream['height']
    st_index = stream['index']

    ff = ffmpeg.Ffmpeg(f'{WORKDIR}/%06d.png').skip('audio')
    ff.filter_complex(f"[1:v][0:{st_index}]overlay,mpdecimate[out]")
    ff.input(infile, None)
    ff.input(f"color=size={width}x{height}:rate={FRAME_RATE}:color=black",
             None).format('lavfi')
    ff.map('[out]')
    ff.time_range(0, 22 * 60)
    ff.extra_args('-vsync', 'vfr', '-frame_pts', '1')
    ff.run()


def read_image(image) -> Iterator[TextLine]:
    """
    Reads the text in an image and returns a list of lines in the format:
        timestamp, text, size, marginR, marginL, marginBottom, and text color
    """
    tool = pyocr.get_available_tools()[0]
#      lang = tool.get_available_languages()[0]
    pil_img = Image.open(image)
    (_, r), (_, g), (_, b) = pil_img.getextrema()
    if sum((r, g, b)) < 192:  # there's no text here
        return []
    builder = pyocr.builders.LineBoxBuilder()
    builder.tesseract_flags.extend(['--oem', '1'])
    lineboxes = tool.image_to_string(pil_img, lang='eng', builder=builder)
    start_time = int(image[-10:-4]) / FRAME_RATE
    results = []
    for linebox in lineboxes:
        ((x1, y1), (x2, y2)) = linebox.position
        r, g, b = text_color(pil_img, x1, y1, x2, y2)
        marginr = pil_img.width - x2
        reduce_margin = min(x1, marginr)
        marginl = x1 - reduce_margin
        marginr -= reduce_margin
        marginv = pil_img.height - y2
        size = y2 - y1
        if has_descenders(linebox.content):
            size = int(size * 1.33)
        else:
            marginv -= int(size * 0.3)
            size = int(size * 1.6)
        cropped = pil_img.crop((x1, y1, x2, y2))
        (_, r), (_, g), (_, b) = cropped.getextrema()
#          yield TextLine(start_time, linebox.content, size,
#                         marginl, marginr, marginv, (r, g, b))
        results.append(TextLine(start_time, linebox.content, size,
                                marginl, marginr, marginv, (r, g, b)))
    sys.stderr.write('=')
    sys.stderr.flush()
    return results


def read_subs(directory) -> Iterator[TextLine]:
    skip_cleanup = getenv('SUBCONVERT_SKIP_CLEANUP')
    sys.stderr.write('Performing OCR...\n')

    images = sorted(glob(f'{directory}/*.png'))
    # find the timestamps for all images
    image_times = [int(image[-10:-4]) / FRAME_RATE for image in images]
    # add an extra "dummy" timestamp
    image_times.append(image_times[-1] + 5)

    pool = Pool()
    results = [pool.apply_async(read_image, (image,)) for image in images]

    for i, result in enumerate(results):
        for line in result.get():
            line.end = image_times[i+1]
            yield line
        if not skip_cleanup:
            os.remove(images[i])
    sys.stderr.write('\n')


def sort_values(values: list[int]) -> list[int]:
    frequency_sort = list(set(values))
    frequency_sort.sort(key=values.count, reverse=True)
    return frequency_sort


def normalize_values(lines: list[TextLine], height: int = 1080,
                     threshold: float = 0.008) -> None:
    """
    Find the most frequently occurring values for size, margin, color, and
    normalize the lines to those values if they are close.
    """
    sizes = sort_values([t.size for t in lines])
    marginsL = sort_values([t.marginl for t in lines])
    marginsR = sort_values([t.marginr for t in lines])
    marginsV = sort_values([t.marginv for t in lines])
    colors = sort_values([t.color for t in lines])

    for line in lines:
        for margin in marginsL:
            if abs(line.marginl - margin) < height * threshold:
                line.marginl = margin
                break
        for margin in marginsR:
            if abs(line.marginr - margin) < height * threshold:
                line.marginr = margin
                break
        for margin in marginsV:
            if abs(line.marginv - margin) < height * threshold:
                line.marginv = margin
                break
        for size in sizes:
            if abs(line.size - size) < threshold:
                line.size = size
                break
        for color in colors:
            if (abs(line.color[0] - color[0]) < threshold * 255 and
                    abs(line.color[1] - color[1]) < threshold * 255 and
                    abs(line.color[2] - color[2]) < threshold * 255):
                line.color = color
                break


def read_subtitles(infile, stream):
    skip_cleanup = getenv('SUBCONVERT_SKIP_CLEANUP')
    subs = Subtitles(stream['width'], stream['height'])

    if os.path.exists(WORKDIR):
        sys.stderr.write('Work directory already present, '
                         'skipping export...\n')
    else:
        os.mkdir(WORKDIR)
        sys.stderr.write('Exporting subpicture subtitles...\n')

    dump_subs(infile, stream)
    lines = []
    for line in read_subs(WORKDIR):
        lines.append(line)
    normalize_values(lines, stream['height'])
    for line in lines:
        color = f'{line.color[2]:02X}{line.color[1]:02X}{line.color[0]:02X}'
        style = subs.style(fontname='Roboto', fontsize=line.size,
                           primarycolour=color)  # , marginl=line.marginl,
#                             marginr=line.marginr, marginv=line.marginv)
        subs.entry(SubtitleEntry(line.content, line.start, line.end,
                                 style.name, marginl=line.marginl,
                                 marginr=line.marginr, marginv=line.marginv))
#          print(line)

    if skip_cleanup:
        sys.stderr.write('Skipping cleanup..\n')
    else:
        os.rmdir(WORKDIR)
    sys.stderr.write('OCR Complete. Please check the output for accuracy.\n')
#      postprocess(subs)
    return subs

# ffmpeg -i video.mkv
#  -f lavfi -i "color=size=1920x1080:rate=10:color=black"
#  -filter_complex "[1:v][0:s]overlay,mpdecimate[out]"
#  -map "[out]"
#  -an
#  -vsync vfr
#  -frame_pts true ocrtest/frames_%06d.png
