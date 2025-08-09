
import json
import subprocess
from shutil import which


def info(filename: str):
    command = ['ffprobe', '-show_chapters', '-show_streams',
               '-print_format', 'json', filename]
    ffprobe = subprocess.Popen(command, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL)
    out, _ = ffprobe.communicate()
    ffprobe.wait()
    return json.loads(out.decode('utf-8'))


class Ffmpeg:
    def __init__(self, output_file: str, command: str | None = None):
        if command:
            self.command = command
        else:
            self.command = which('ffmpeg')
        self.output_file = output_file
        self.inputs = []
        self.output_map = []
        self.filters = []
        self.loglevel = None
        self.skip_streams = []
        self.extra_arguments = []
        self.start_time = 0
        self.end_time = 0
        self.proc:subprocess.Popen = None

    def time_range(self, start: float | int = 0, end: float | int = 0):
        self.start_time = start
        self.end_time = end

    def loglevel(self, loglevel: str):
        self.set_loglevel = loglevel
        return self

    def input(self, filename: str, stream: int | str | None = None):
        self.inputs.append(_Ffmpeg_input(filename))
        if stream is not None:
            self.map(len(self.inputs), stream)
        return self.inputs[-1]

    def map(self, index, stream=None):
        self.output_map.append(_Ffmpeg_output_map(index, stream))
        return self.output_map[-1]

    def filter_complex(self, filter_str: str):
        self.filters.append(_Ffmpeg_filter_complex(filter_str))

    def skip(self, stream_type):
        if stream_type in ('video', 'audio', 'subtitle', 'data'):
            self.skip_streams.append(stream_type)
        return self

    def extra_args(self, *args):
        self.extra_arguments.extend(args)
        return self

    def get_command(self):
        command = [self.command, '-y']
        if self.loglevel:
            command.append('-loglevel')
            command.append(self.loglevel)
        for i in self.inputs:
            command.extend(i.args())
        for fc in self.filters:
            command.extend(fc.args())
        for o in self.output_map:
            command.extend(o.args())
        for s in self.skip_streams:
            if s == 'video':
                command.append('-vn')
            if s == 'audio':
                command.append('-an')
            if s == 'subtitle':
                command.append('-sn')
            if s == 'data':
                command.append('-dn')
        command.extend(self.extra_arguments)
        if (self.start_time > 0):
            command.append('-ss')
            command.append(str(self.start_time))
        if (self.end_time > 0):
            command.append('-to')
            command.append(str(self.end_time))
        command.append(self.output_file)
        return command

    def start(self):
        self.proc = subprocess.Popen(
                self.get_command(),  stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)

    def wait(self):
        if self.proc:
            self.proc.wait()
        self.proc = None

    def is_running(self):
        return self.proc.is_running()

    def run(self):
        if not self.proc:
            self.start()
        self.wait()


class _Ffmpeg_input:
    def __init__(self, filename: str, file_format: str | None = None):
        self.filename = filename
        self.file_format = file_format
        self.time_offset = 0

    def format(self, file_format):
        self.file_format = file_format
        return self

    def time_offset(self, offset: float):
        self.offset = offset
        return self

    def args(self):
        args = []
        if self.file_format:
            args.append('-f')
            args.append(self.file_format)
        if self.time_offset:
            args.append('-itsoffset')
            args.append(str(self.time_offset))
        args.append('-i')
        args.append(self.filename)
        return args


class _Ffmpeg_output_map:
    def __init__(self, index: int | str, stream: int | None = None):
        self.index = index
        self.stream = stream

    def args(self):
        spec = str(self.index)
        if self.stream is not None:
            spec = f'{self.index}:{self.stream}'
        return ['-map', spec]


class _Ffmpeg_filter_complex:
    def __init__(self, filter_str: str):
        self.filter = filter_str

    def args(self):
        return ['-filter_complex', self.filter]
