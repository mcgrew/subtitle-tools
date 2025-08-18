
import subprocess
import sys
import os
from shutil import which
from dataclasses import dataclass
from typing import Iterable


@dataclass
class Font:
    filename: str
    names: Iterable[str]
    styles: Iterable[str]

    def __post_init__(self):
        self.names = tuple(n.lower() for n in self.names)
        self.styles = tuple(s.lower() for s in self.styles)

    def has_name(self, name: str):
        return name.lower() in self.names

    def has_style(self, style: str):
        return style.lower() in self.styles

    def __str__(self):
        return (f'{self.filename}:{",".join(self.names)}:'
                f'{",".join(self.styles)}')

    def __lt__(self, font):  # define this so we can sort
        thisfile = os.path.basename(self.filename[:self.filename.rindex('.')])
        otherfile = os.path.basename(font.filename[:font.filename.rindex('.')])
        return thisfile.__lt__(otherfile)


def _reg_query():  # windows (hopefully this works)
    command = ('wine', 'reg', 'query',
               'HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts')
    query = subprocess.Popen(command, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
    out, _ = query.communicate()
    query.wait()

    style_search = ('regular', 'bold', 'extrabold', 'italic', 'oblique',
                    'condensed', 'light', 'thin', 'medium', 'heavy')
    fonts = []
    for line in out.decode('utf-8').split('\n'):
        line = line.strip()
        if not line or 'HKEY_LOCAL_MACHINE' in line:
            continue
        filename = line[line.rindex(' ') + 1:]
        name = line[1:line.index(' ')].lower()  # strip the @ at the beginning
        styles = [s for s in style_search if s in name]
        if not styles:
            styles = ['regular']
        fonts.append(Font(filename, [name], styles))
    return fonts


def _parse_fc_list(command):
    fc_list = subprocess.Popen([command], stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    out, _ = fc_list.communicate()
    fc_list.wait()
    fonts = []
    for line in out.decode('utf-8').split('\n'):
        if ':' not in line:
            continue
        styles = ['regular']
        if line.count(':') < 2:
            filename, font_name = [f.strip() for f in line.split(':')]
        else:
            filename, font_name, styles = [f.strip() for f
                                           in line.split(':', 2)]
            styles = styles[styles.index('=') + 1:].split(',')
        names = font_name.split(',')
        fonts.append(Font(filename, names, styles))
    return sorted(fonts)


def _populate():
    command = which('fc-list')
    if command:
        return _parse_fc_list(command)
    command = which('reg')
    if command:
        return _reg_query()
    sys.stderr.write('Unable to determine system fonts\n')


def get_all(name: str, style: str | None = None):
    fonts = []
    for font in installed:
        if font.has_name(name) and (not style or font.has_style(style)):
            fonts.append(font)
    return fonts


def fuzzy_name(name: str, style: str | None = None):
    fonts = []
    for font in installed:
        if (any([(name in fn) for fn in font.names])
                and (not style or font.has_style(style))):
            fonts.append(font)
    return fonts


def get(font_name: str, style: str = 'regular'):
    font_name = font_name.lower()
    for font in installed:
        if font.has_name(font_name):
            if font.has_style(style):
                return font
    for font in installed:
        if font.has_name(font_name):
            if font.has_style('regular'):
                return font
    for font in installed:
        if font.has_name(font_name):
            return font


def find_file(query: str):
    return [f for f in installed if query in f.filename]


installed = _populate()


if __name__ == '__main__':
    f = installed
    if len(sys.argv) > 1:
        f = fuzzy_name(' '.join(sys.argv[1:]))
    for i in f:
        print(i)
