
import os
import sys
import tesseract
from typing import Iterator
from dataclasses import dataclass
from glob import glob
from multiprocessing.pool import Pool
from shutil import which
from PIL import Image, ImageOps

import subprocess

import ffmpeg
from subtitles import Subtitles, SubtitleEntry

FRAME_RATE = 10
WORKDIR = '/tmp/work'


@dataclass
class TextLine:
    start: float
    content: str
    size: int
    italic: bool
    bold: bool
    marginl: int
    marginr: int
    marginv: int
    color: tuple[int, int, int]
    end: float = 0

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


def dump_subs(infile, stream, duration):
    width = stream['width']
    height = stream['height']
    st_index = stream['index']

    ff = ffmpeg.Ffmpeg(f'{WORKDIR}/%06d.png').skip('audio')
    ff.filter_complex(f"[1:v][0:{st_index}]overlay,mpdecimate")
    ff.input(infile, None)
    ff.input(f"color=size={width}x{height}:rate={FRAME_RATE}:color=black"
             f":duration={duration}", None).format('lavfi')
    ff.extra_args('-vsync', 'vfr', '-frame_pts', '1')
    ff.run()


def fix_common(text: str | tesseract.Line | tesseract.Word):
    """
    Tesseract sometimes returns fancy quotes and other characters instead of
    normal ones. This will swap those out.
    This also corrects some common misreads.
    """
    replacements = {
            '| ': 'I ',
            '/ ': 'I ',
            '1?': 'I?',
            '\u2019': "'",
            '\u201d': '"',
            '\u201c': '"',
    }
    text = str(text).strip()
    for err, repl in replacements.items():
        if err in text:
            text = text.replace(err, repl)
    return text


class SpellChecker:
    def __init__(self):
        self.checker = which('ispell') or which('aspell')

    def check(self, detection_list):
        """
        This all looks super complicated, so let me explain:

        I'm taking the array of passed in strings, splitting them on the word
        boundary, sorting each word position by frequency, and then running
        them through a spell checker.

        The first correct hit on each word gets used, but if none hit, the most
        frequent occurrence is used instead.
        """
        words = zip(*(d.split() for d in detection_list))
        words = [sorted(w, key=w.count, reverse=True) for w in words]
        if not self.checker:
            return ' '.join(w[0] for w in words)
        spell_input = '\n'.join(' '.join(w for w in x) for x in words)
        spell = subprocess.Popen([self.checker, '-a'], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL)
        out, _ = spell.communicate(spell_input.encode('utf-8'))
        out = (o.split('\n') for o in out.decode('utf-8').split('\n\n'))
        final_string = []
        for line, line_result in zip(words, out):
            for word, result in zip(line, line_result):
                if result == '*':
                    final_string.append(word)
                    break
            else:  # yes this is weird, look up how python for else works
                # this happens if none of the words get a hit in ispell
                final_string.append(line[0])
        return ' '.join(final_string)


def verify_text(text0: str, text1: str, cropped: tuple[Image]):
    if text0 == text1:
        return text0
    detected = [text0, text1]
    sys.stderr.write(f'Checking: {text0} | {text1}\n')
    detected.append(tesseract.simple_read(cropped[1], oem=3))

    scaled = [c.resize((int(c.width * 0.75),
              int(c.height * 0.75))) for c in cropped]
    detected.append(tesseract.simple_read(scaled[1], oem=1))
    detected.append(tesseract.simple_read(scaled[0], oem=0))

    scaled = [c.reduce(2) for c in cropped]
    detected.append(tesseract.simple_read(scaled[1], oem=1))
    detected.append(tesseract.simple_read(scaled[0], oem=0))
    result = SpellChecker().check(detected)
    sys.stderr.write(f'{text1} -> {result}\n')
    return result


def read_image(image: str) -> Iterator[TextLine]:
    """
    Reads the text in an image and returns a list of lines in the format:
        timestamp, text, size, marginR, marginL, marginBottom, and text color

    args:
        image: The path to the image
    """
    pil_img = Image.open(image)
    tess0_img = ImageOps.grayscale(pil_img)
    tess1_img = ImageOps.invert(tess0_img)
    (_, r), (_, g), (_, b) = pil_img.getextrema()
    if sum((r, g, b)) < 192:  # there's no text here
        return []
    lines0 = tesseract.read_image(tess0_img, oem=0)
    lines1 = tesseract.read_image(tess1_img, oem=1)
    # check for a mismatch in the number of lines detected.
    # in practice this should never happen, but...
    match cmp := len(lines0) - len(lines1):
        case 0:
            pass
        case _ if cmp < 0:
            sys.stderr.write('ERROR: LINE COUNT MISMATCH!\n')
            lines0 = lines1
        case _ if cmp > 0:
            sys.stderr.write('ERROR: LINE COUNT MISMATCH!\n')
            lines1 = lines0

    start_time = int(image[-10:-4]) / FRAME_RATE
    results = []
    for line0, line1 in zip(lines0, lines1):
        x1, y1, x2, y2 = line0.bbox
        marginr = pil_img.width - x2
        reduce_margin = min(x1, marginr)
        marginl = x1 - reduce_margin
        marginr -= reduce_margin
        marginv = (pil_img.height - y2)
        text0 = fix_common(line0)
        text1 = fix_common(line1)
        verify_img = (tess0_img.crop((x1-10, y1-10, x2+10, y2+10)),
                      tess1_img.crop((x1-10, y1-10, x2+10, y2+10)))
        text = verify_text(text0, text1, verify_img)

        size = line1.size * 1.5
        if has_descenders(text):
            marginv -= int(size * 0.05)
        else:
            marginv -= int(size * 0.3)
        # find the most frequent color that's not dark
        cropped = pil_img.crop((x1, y1, x2, y2))
        colors = [c for c in cropped.getdata() if sum(c) >= 400]
        sorted_colors = sorted([c for c in set(colors)], key=colors.count,
                               reverse=True)
        if sorted_colors[0][0] == 1:
            cropped.save(image.replace('work', 'cropped'))
        results.append(TextLine(start_time, text, size, line0.italic,
                                line0.bold, marginl, marginr,
                                marginv, sorted_colors[0]))
    return results


def read_subs(directory) -> Iterator[TextLine]:
    skip_cleanup = getenv('SUBCONVERT_SKIP_CLEANUP')
    if skip_cleanup:
        sys.stderr.write("Temporary images will not be removed.\n")
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


def read_subtitles(infile, stream, duration):
    skip_cleanup = getenv('SUBCONVERT_SKIP_CLEANUP')
    subs = Subtitles(stream['width'], stream['height'])

    if os.path.exists(WORKDIR):
        sys.stderr.write('Work directory already present, '
                         'skipping export...\n')
    else:
        os.mkdir(WORKDIR)
        sys.stderr.write('Exporting subpicture subtitles...\n')

    dump_subs(infile, stream, duration)
    lines = list(read_subs(WORKDIR))
    normalize_values(lines, stream['height'])
    merge_lines(lines)
    for line in [s for s in lines if s.end >= 0]:
        color = f'{line.color[2]:02X}{line.color[1]:02X}{line.color[0]:02X}'
        style = subs.style(fontname='Open Sans SemiBold', fontsize=line.size,
                           primarycolour=color, italic=line.italic,
                           bold=line.bold)  # , marginl=line.marginl,
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
