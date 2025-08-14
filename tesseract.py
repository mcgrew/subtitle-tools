
import subprocess
from xml.etree import ElementTree
from collections import namedtuple
from io import BytesIO

from PIL import Image

Bbox = namedtuple('Bbox', ['x1', 'y1', 'x2', 'y2'])


class Word:
    def __init__(self, word_el: ElementTree.Element):
        self.italic = False
        self.bold = False
        self.unknown_style = []
        attrs = word_el.get('title')
        for attr in (a.strip() for a in attrs.split(';')):
            if attr.startswith('bbox '):
                self.bbox = Bbox(*[int(coord) for coord in attr[5:].split()])
            if attr.startswith('x_wconf '):
                self.confidence = int(attr[8:])
        self.text = (' '.join(word_el.itertext())).strip()
        sub_els = word_el.findall('.//')
        for el in sub_els:
            match el.tag[el.tag.index('}') + 1:]:
                case 'em':
                    self.italic = True
                case 'strong':
                    self.bold = True
                case t:
                    self.unknown_style.append(t)

    def __str__(self):
        return self.text

    def __repr__(self):
        return f'{self.text} ({self.bbox}, conf {self.confidence})'


class Line:
    def __init__(self, line_el: ElementTree.Element):
        self._parse_attrs(line_el.get('title'))
        word_els = line_el.findall('.//{http://www.w3.org/1999/xhtml}'
                                   'span[@class="ocrx_word"]')
        self.words = [Word(el) for el in word_els]
        self.confidence = (sum((w.confidence for w in self.words))
                           / len(self.words))
        self.italic = all((w.italic for w in self.words))
        self.bold = all((w.bold for w in self.words))
        self.has_italic = any((w.italic for w in self.words))
        self.has_bold = any((w.bold for w in self.words))

    def _parse_attrs(self, attrs: str):
        attr_list = (a.strip() for a in attrs.split(';'))
        for attr in attr_list:
            if attr.startswith('bbox '):
                self.bbox = Bbox(*(int(coord) for coord in attr[5:].split()))
            if attr.startswith('baseline '):
                b = attr[9:].split()
                self.baseline = (float(b[0]), int(b[1]))
            if attr.startswith('x_size '):
                self.size = float(attr[7:])
            if attr.startswith('x_descenders '):
                self.descenders = float(attr[13:])
            if attr.startswith('x_ascenders '):
                self.ascenders = float(attr[12:])

    def __str__(self):
        return ' '.join((word.text for word in self.words))

    def __repr__(self):
        return (f'{str(self)} ({self.bbox}, conf {self.confidence:.2f} '
                f'{"italic " if self.has_italic else ""}'
                f'{"bold" if self.has_bold else ""}')


def build_lines(tess_output: str):
    tree = ElementTree.fromstring(tess_output)
    line_els = tree.findall('.//{http://www.w3.org/1999/xhtml}'
                            'span[@class="ocr_line"]')
    return [Line(el) for el in line_els]


def read_image(image: str | Image.Image, engine: int = 0):
    if isinstance(image, str):
        image = Image.open(image)
    command = ['tesseract', '-', '-', '--oem', str(engine), 'hocr']
    tesseract = subprocess.Popen(command, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL)
    png = BytesIO()
    image.save(png, 'png')
    png.seek(0)
    out, _ = tesseract.communicate(png.read())
    tesseract.wait()
    return build_lines(out)


if __name__ == '__main__':  # test code
    import sys
    engine = 0
    if len(sys.argv) > 2:
        engine = int(sys.argv[2])
    for line in read_image(sys.argv[1], engine):
        print(repr(line))
