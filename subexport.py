#!/usr/bin/env python3

import sys
from argparse import ArgumentParser

import ffmpeg
#  import subtitles

try:
    import ocr
except ImportError:
    ocr = None

SUBP_CODECS = ('hdmv_pgs_subtitle', 'dvd_subtitle', 'dvb_subtitle')


def main(args):

    info = ffmpeg.info(args.input)
    duration = float(info["format"]["duration"])
    sub_streams = []
    for stream in info['streams']:
        match stream['codec_type']:
            case 'subtitle':
                sub_streams.append(stream)

    if not sub_streams:
        sys.stderr.write('No subtitles found in the input file, exiting...')
        exit(-1)

#      if not args.output and not args.output_format:
#          sys.stderr.write(
#                  'No output file or output format specified, aborting...')
#          exit(-1)
#
    if args.output_format in ('ass', None):
        args.output_format = 'ssa'
    if not args.output_format:
        match args.output[-4:]:
            case '.srt':
                args.output_format = 'srt'
            case '.ssa' | '.ass':
                args.output_format = 'ssa'

    input_stream = sub_streams[args.subtitle_stream]
    if len(sub_streams) > 1:
        sys.stderr.write(f'Using subtitle stream {args.subtitle_stream} - '
                         f'{input_stream["codec_long_name"]}\n')
    if input_stream['codec_name'] in SUBP_CODECS:
        if not ocr:
            sys.stderr.write('OCR unsupported - make sure you have pyocr and '
                             'pytesseract installed.\n')
            sys.stderr.write('Unable to convert subpicture subtitles.')
            exit(-1)
        subs = ocr.read_subtitles(args.input, input_stream, duration)
    else:
        sys.stderr.write('Text subtitles are not yet supported for input. '
                         'Coming soon!')
        exit(-1)

    with open(args.output, 'w') if args.output else sys.stdout as outputfile:
        match args.output_format:
            case 'ssa':
                outputfile.write(subs.ssa())
            case 'srt':
                outputfile.write(subs.srt())


if __name__ == '__main__':
    argparser = ArgumentParser()
    argparser.add_argument('-i', '--input', required=True)
    argparser.add_argument('-s', '--subtitle-stream', type=int, default=0)
    argparser.add_argument('-o', '--output', default=None)
    argparser.add_argument('-f', '--output-format', default=None)
    argparser.add_argument('--ssa-font', default='Roboto')
    main(argparser.parse_args())
