#!/usr/bin/env python3

import sys
from argparse import ArgumentParser

import ffmpeg
import ocr
#  import subtitles

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

    if not args.output_format and args.output:
        match args.output[-4:]:
            case '.srt':
                args.output_format = 'srt'
            case '.ssa' | '.ass':
                args.output_format = 'ssa'
    if args.output_format in ('ass', None):
        args.output_format = 'ssa'

    input_stream = sub_streams[args.subtitle_stream]
    if len(sub_streams) > 1:
        sys.stderr.write(f'Using subtitle stream {args.subtitle_stream} - '
                         f'{input_stream["codec_long_name"]}\n')
    if input_stream['codec_name'] in SUBP_CODECS:
        subs = ocr.read_subtitles(args.input, input_stream, duration,
                                  args.font, args.skip_formatting)
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
    argparser = ArgumentParser(usage="Subtitle-tools v0.1-pre\n"
                               "This application is intended to convert\n"
                               "subpicture-based subtitles into ssa/srt\n"
                               "format.\n"
                               "Currently supported languages: English.")
    argparser.add_argument('-i', '--input', required=True,
                           help="The input file. Currently this should be a "
                           "video file containing subtittles.")
    argparser.add_argument('-s', '--subtitle-stream', type=int, default=0,
                           help="Which subtitle stream to read from the video "
                           "file. Default is the first subpicture stream.")
    argparser.add_argument('-o', '--output', default=None,
                           help="The file name for output. If unspecified, "
                           "the file will be writtent to stdout.")
    argparser.add_argument('-f', '--output-format', default=None,
                           help="The output format for the subtitle file. "
                           "Currently supported formats are ssa and srt. The "
                           "default is ssa.")
    argparser.add_argument('-t', '--font', default="FreeSans Bold",
                           help="Specify a font for all subtitles. Default is "
                           "'FreeSans'.")
    argparser.add_argument('-k', '--skip-formatting', action="store_true",
                           help="Skip all position and font size detection. "
                           "This is useful for import into a subtitle editor "
                           "when you want to perform manual formatting.")
    main(argparser.parse_args())
