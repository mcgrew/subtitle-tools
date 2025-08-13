
import os
import sys
import pyocr
from collections import defaultdict
from typing import Iterator
from dataclasses import dataclass
from glob import glob
from multiprocessing.pool import Pool
from PIL import Image, ImageOps

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
                        .replace('/ ', 'I ')
                        .replace('1?', 'I?'))

    def __cmp__(self, textline):
        if self.start < textline.start:
            return -1
        if self.start > textline.start:
            return 1
        if self.marginv < textline.marginv:
            return -1
        if self.marginv > textline.marginv:
            return 1
        return 0

    def is_mergeable_with(self, line: 'TextLine'):
        """
        Determines whether 2 lines that are above one another should be merged
        into one.
        """
        return (self.start == line.start and self.end == line.end
                and self.size == line.size and self.color == line.color
                and self.marginv - line.size - line.marginv < line.size//10)

    def continues_to(self, line: 'TextLine'):
        """
        Determines whether the passed in TextLine is a continuation of this
        one.
        """
        return (abs(self.end - line.start) < 0.1
                and self.content == line.content and self.size == line.size
                and self.color == line.color and self.marginv == line.marginv
                and self.marginl == line.marginl
                and self.marginr == line.marginr)


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


def verify_text(text: str, cropped: Image):
    scaled = cropped.resize((int(cropped.width * 0.75),
                             int(cropped.height * 0.75)))
    sys.stderr.write(f'Checking: {text}\n')
    tool = pyocr.get_available_tools()[0]
    builder = pyocr.builders.TextBuilder()
    builder.tesseract_flags.extend(['--oem', '1'])
    text2 = tool.image_to_string(scaled, lang='eng', builder=builder)
    if text == text2:
        sys.stderr.write(f'Verified: {text}\n')
        return text
    scaled = cropped.reduce(2)
    builder.tesseract_flags.extend(['--oem', '1'])
    text3 = tool.image_to_string(scaled, lang='eng', builder=builder)
    if text3 and text3 == text2:
        sys.stderr.write(f'Corrected: {text} -> {text3}\n')
        return text3
    if text3 != text:
        sys.stderr.write(f'Could not verify text: {text}, {text2}, {text3}\n')
    return text


def read_image(image: str, oem: int = 1) -> Iterator[TextLine]:
    """
    Reads the text in an image and returns a list of lines in the format:
        timestamp, text, size, marginR, marginL, marginBottom, and text color

    args:
        image: The path to the image
        oem: The tesseract engine to use:
             0 = Original Tesseract only.
             1 = Neural nets LSTM only.
             2 = Tesseract + LSTM.
             3 = System default, based on what is available.
    """
    tool = pyocr.get_available_tools()[0]
#      lang = tool.get_available_languages()[0]
    pil_img = Image.open(image)
    tess_img = ImageOps.invert(ImageOps.grayscale(pil_img))
    (_, r), (_, g), (_, b) = pil_img.getextrema()
    if sum((r, g, b)) < 192:  # there's no text here
        return []
    builder = pyocr.builders.LineBoxBuilder()
    builder.tesseract_flags.extend(['--oem', str(oem)])
    lineboxes = tool.image_to_string(tess_img, lang='eng', builder=builder)
    start_time = int(image[-10:-4]) / FRAME_RATE
    results = []
    for linebox in lineboxes:
        ((x1, y1), (x2, y2)) = linebox.position

        marginr = pil_img.width - x2
        reduce_margin = min(x1, marginr)
        marginl = x1 - reduce_margin
        marginr -= reduce_margin
        marginv = (pil_img.height - y2)
        text = linebox.content

        if text.upper() == text or '0' in text:
            verify = tess_img.crop((x1-10, y1-10, x2+10, y2+10))
            text = verify_text(text, verify)
        size = (y2 - y1)
        if has_descenders(text):
            size = int(size * 1.33)
        else:
            marginv -= int(size * 0.3)
            size = int(size * 1.6)
        # find the most frequent color that's not dark
        cropped = pil_img.crop((x1, y1, x2, y2))
        colors = [c for c in cropped.getdata() if sum(c) >= 400]
        sorted_colors = sorted([c for c in set(colors)], key=colors.count, reverse=True)
        if sorted_colors[0][0] == 1:
            cropped.save(image.replace('work', 'cropped'))
#          sorted_colors.sort(key=colors.count)
#          sys.stderr.write(str(sorted_colors[:10]) + '\n')
        results.append(TextLine(start_time, text, size, marginl, marginr,
                                marginv, sorted_colors[0]))
#      sys.stderr.write('=')
#      sys.stderr.flush()
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


def freq_sort(values: list[int]) -> list[int]:
    all_values = list(set(values))
    all_values.sort(key=values.count, reverse=True)
    return all_values


def normalize_values(lines: list[TextLine], height: int = 1080,
                     tolerance: float = 0.008) -> None:
    """
    Find the most frequently occurring values for size, margin, color, and
    normalize the lines to those values if they are close.
    """
    sizes = freq_sort([t.size for t in lines])
    marginsL = freq_sort([t.marginl for t in lines])
    marginsR = freq_sort([t.marginr for t in lines])
    marginsV = freq_sort([t.marginv for t in lines])
    colors = freq_sort([t.color for t in lines])

    for line in lines:
        for margin in marginsL:
            if abs(line.marginl - margin) < height * tolerance:
                line.marginl = margin
                break
        for margin in marginsR:
            if abs(line.marginr - margin) < height * tolerance:
                line.marginr = margin
                break
        for margin in marginsV:
            if abs(line.marginv - margin) < height * tolerance:
                line.marginv = margin
                break
        for size in sizes:
            if abs(line.size - size) < height * tolerance:
                line.size = size
                break
        for color in colors:
            if (abs(line.color[0] - color[0]) < 32
                    and abs(line.color[1] - color[1]) < 32
                    and abs(line.color[2] - color[2]) < 32):
                line.color = color
                break


def merge_lines(lines: list[TextLine]):
    for i, line1 in enumerate(lines):
        if line1.end < 0:
            continue
        for line2 in lines[i+1:]:
            if line2.end < 0:
                continue
            if line1.is_mergeable_with(line2):
                line1.content += '\\N' + line2.content
                line1.marginv = line2.marginv
                line2.start = line2.end = -1.0  # mark this line for later
    for i, line1 in enumerate(lines):
        if line1.end < 0:
            continue
        for line2 in lines[i+1:]:
            if line2.end < 0:
                continue
            if line1.continues_to(line2):
                line1.end = line2.end
                line2.start = line2.end = -1.0  # mark this line for later


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
    lines = list(read_subs(WORKDIR))
    normalize_values(lines, stream['height'])
    merge_lines(lines)
    for line in [s for s in lines if s.end >= 0]:
        color = f'{line.color[2]:02X}{line.color[1]:02X}{line.color[0]:02X}'
        style = subs.style(fontname='Roboto', fontsize=line.size,
                           primarycolour=color)  # , marginl=line.marginl,
#                             marginr=line.marginr, marginv=line.marginv)
        subs.entry(SubtitleEntry(line.content, line.start, line.end,
                                 style.name, marginl=line.marginl,
                                 marginr=line.marginr, marginv=line.marginv))

    if skip_cleanup:
        sys.stderr.write('Skipping cleanup..\n')
    else:
        os.rmdir(WORKDIR)
    sys.stderr.write('OCR Complete. Please check the output for accuracy.\n')
    return subs

# ffmpeg -i video.mkv
#  -f lavfi -i "color=size=1920x1080:rate=10:color=black"
#  -filter_complex "[1:v][0:s]overlay,mpdecimate[out]"
#  -map "[out]"
#  -an
#  -vsync vfr
#  -frame_pts true ocrtest/frames_%06d.png
