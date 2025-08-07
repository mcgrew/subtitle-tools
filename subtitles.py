
from io import StringIO


class SubtitleEntry:
    def __init__(self, text, start, end, style='Default', name='',
                 marked=0, marginl=0, marginr=0, marginv=0, effect='',
                 size=36, color=(255, 255, 255)):
        self.text = text
        self.start = start
        self.end = end
        self.marked = int(marked)
        self.style = style
        self.name = name
        self.marginl = int(marginl)
        self.marginr = int(marginr)
        self.marginv = int(marginv)
        self.effect = effect
        self.size = size
        self.color = self._color_hex(color)

    def _color_hex(self, color: tuple[int]):
        return f'{color[2]:02X}{color[1]:02X}{color[0]:02X}'

    def _ts(self, sec: float, format='ssa'):
        ms = (sec % 1)
        sec = int(sec)
        if format == 'ssa':
            return (f'{int(sec / 3600):1d}:{int(sec / 60 % 60):02d}:'
                    f'{sec % 60:02d}.{int(ms * 100):02d}')
        return (f'{int(sec / 3600):02d}:{int(sec / 60 % 60):02d}:'
                f'{sec % 60:02d},{int(ms * 1000):03d}')

    def srt(self):
        return (f'{self._ts(self.start, "srt")} --> '
                f'{self._ts(self.end, "srt")}\n'
                f'{self.text}\n')

    def ssa(self):
        return (f'Dialogue: Marked={self.marked},{self._ts(self.start)},'
                f'{self._ts(self.end)},{self.style},{self.name},'
                f'{self.marginl:04d},{self.marginr:04d},{self.marginv:04d},'
                f'{self.effect},{self.text.replace("\n", "\\n")}\n')

    def __eq__(self, subtitle_entry):
        return self.text == subtitle_entry.text


class SubComment:
    def __init__(self, text):
        self.start = self.end = 0
        self.text = text

    def srt(self):
        return ''

    def ssa(self):
        return f'; {self.text}\n'


class SubtitleSyle:
    def __init__(self, name, fontname, fontsize=24,
                 primarycolour='FFFFFF', secondarycolour='FFFFFF',
                 tertiarycolour='000000', backcolour='000000',
                 bold=-1, italic=0, borderstyle=1, outline=2,
                 shadow=3, alignment=2, marginl=20, marginr=20,
                 marginv=20, alphalevel=0, encoding=1):
        self.name = name
        self.fontname = fontname
        self.fontsize = int(fontsize)
        self.primarycolour = primarycolour
        self.secondarycolour = secondarycolour
        self.tertiarycolour = tertiarycolour
        self.backcolour = backcolour
        self.bold = int(bold)
        self.italic = int(italic)
        self.borderstyle = int(borderstyle)
        self.outline = int(outline)
        self.shadow = int(shadow)
        self.alignment = int(alignment)
        self.marginl = int(marginl)
        self.marginr = int(marginr)
        self.marginv = int(marginv)
        self.alphalevel = int(alphalevel)
        self.encoding = int(encoding)

    def __str__(self):
        return (f'Style: {self.name},{self.fontname},{self.fontsize},'
                f'&H{self.primarycolour},&H{self.secondarycolour},'
                f'&H{self.tertiarycolour},&H{self.backcolour},'
                f'{self.bold},' f'{self.italic},'
                f'{self.borderstyle},{self.outline},'
                f'{self.shadow},{self.alignment},{self.marginl},'
                f'{self.marginr},{self.marginv},{self.alphalevel},'
                f'{self.encoding}')


class Subtitles:
    def __init__(self, width=1920, height=1080):
        self.entries: list[SubtitleEntry] = []
        self.styles: dict[str, SubtitleSyle] = {}
        self.width = int(width)
        self.height = int(height)

#      def __init__(self, name, fontname, fontsize=24,
#                   primarycolour=0xffffff, secondarycolour=0xffffff,
#                   tertiarycolour=0x000000, backcolour=0x000000,
#                   bold=-1, italic=0, borderstyle=1, outline=2,
#                   shadow=3, alignment=2, marginl=20, marginr=20,
#                   marginv=10, alphalevel=0, encoding=1):

    def entry(self, entry: SubtitleEntry):
        self.entries.append(entry)

    def comment(self, text):
        self.entries.append(SubComment(text))

    def style(self, name, fontname, **kwargs):
        s = self.styles[name] = SubtitleSyle(name, fontname, **kwargs)
        return s

    def srt(self):
        buf = StringIO()
        for i, entry in enumerate(self.entries):
            buf.write(f'{i + 1}\n{entry.srt()}\n')
        buf.seek(0)
        return buf.read()

    def ssa(self):
        buf = StringIO()
        buf.write('[Script Info]\n')
        buf.write('; This is a Sub Station Alpha v4 script.\n')
        buf.write('; For Sub Station Alpha info and downloads,\n')
        buf.write('; go to http://www.eswat.demon.co.uk/\n')
        buf.write('; or email kotus@eswat.demon.co.uk\n')
        buf.write('; \n')
        buf.write('; Note: This file was created with pysubtools.\n')
        buf.write('; \n')
        buf.write('ScriptType: v4.00\n')
        buf.write('Collisions: Normal\n')
        buf.write(f'PlayResX: {self.width}\n')
        buf.write(f'PlayResY: {self.height}\n')
        buf.write('Timer: 100.0000\n\n')

        buf.write('[V4 Styles]\n')
        buf.write('Format: Name, Fontname, Fontsize, PrimaryColour, '
                  'SecondaryColour, TertiaryColour, BackColour, Bold, '
                  'Italic, BorderStyle, Outline, Shadow, Alignment, '
                  'MarginL, MarginR, MarginV, AlphaLevel, Encoding\n')
        for style in self.styles.values():
            buf.write(f'{style}\n')
        buf.write('\n[Events]\n')
        buf.write('Format: Marked, Start, End, Style, Name, MarginL, MarginR, '
                  'MarginV, Effect, Text\n')

        for entry in self.entries:
            if entry.end < 0:
                return ''
            if entry.start < 0:
                entry.start = 0
            buf.write(entry.ssa())
        buf.seek(0)
        return buf.read()

    def dump(self, sub_format):
        if sub_format == 'srt':
            return self.srt()
        else:
            return self.ssa()
