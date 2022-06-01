#! /usr/bin/env python3

default_profile = 'fbot-sandbox'
debug = False
delay_sleep = 0.4 # seconds

import datetime
import time

import argparse
import base64
import json
import os
import pathlib
import pprint
import re
import sys

pp = pprint.PrettyPrinter(indent=4, compact=True)

# Use awscli's virtualenv if we're not already running in one.
if 'VIRTUAL_ENV' not in os.environ:
    print('using awscli virtualenv', file=sys.stderr)
    activate_script = pathlib.Path('/usr/local/bin/aws').resolve().parent.joinpath('activate_this.py')
    exec(open(activate_script).read(), dict(__file__=activate_script))

print(os.environ['VIRTUAL_ENV'], file=sys.stderr)

def parse_since(since):
    """ Parses a "since" value and converts it to seconds."""
    multiplier = {
        '': 1,
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 24 * 3600,
    }
    since_re = re.compile(r'^(\d+)([smdh]?)$');
    match = since_re.match(since)
    if not match:
        raise ValueError('since is not in format "INT[smhd]?"')
    return int(match.group(1)) * multiplier[match.group(2)]

def handle_event(rec):
    rec['Data'] = json.loads(base64.b64decode(rec['Data']))

handler = {
    'fbt-event': handle_event,
}

class bcolors:
    HEADER      = '\033[95m'    # bright magenta
    OKBLUE      = '\033[94m'    # bright blue
    OKCYAN      = '\033[96m'    # bright cyan
    OKGREEN     = '\033[92m'    # bright green
    WARNING     = '\033[93m'    # bright yellow
    FAIL        = '\033[91m'    # bright red
    ENDC        = '\033[0m'
    BOLD        = '\033[1m'
    UNDERLINE   = '\033[4m'
    GREY0       = f'\033[38;5;{232 +  0}m' # black
    GREY10      = f'\033[38;5;{232 + 10}m'
    GREY20      = f'\033[38;5;{232 + 20}m'
    GREY23      = f'\033[38;5;{232 + 23}m' # white


# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/session.html
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/kinesis.html

import botocore.session

def dump_stream(stream, profile, **opts):
    session = botocore.session.Session(profile=profile)
    client = session.create_client('kinesis')

    # A Kinesis stream may consist of one or more shards.  Each shard can
    # handle 1 MB/S of writes, 2 MB/S of reads, or 1000 records per second.
    # Records that are put onto the stream have a key that is hashed to
    # determine which shard to send the record to.  Friendbuy does not use
    # more than one shard for any of its Kinesis streams.

    shards = client.list_shards(StreamName=stream)
    if debug: print(f'{bcolors.GREY20}shards\n{pp.pformat(shards)}{bcolors.ENDC}', file=sys.stderr)
    shard_count = len(shards['Shards'])
    if shard_count > 1:
        raise Exception(f'shard count {shard_count} > 1 not handled')
    shard_id = shards['Shards'][0]['ShardId']

    if opts.get('start', 0):
        # print(f'using start {opts["start"]}', file=sys.stderr)
        shard_iterator_opts = { 'ShardIteratorType': 'AT_TIMESTAMP', 'Timestamp': opts['start'] }
    else:
        # print('using trim_horizon', file=sys.stderr)
        shard_iterator_opts = { 'ShardIteratorType': 'TRIM_HORIZON' }

    r = client.get_shard_iterator(
        StreamName=stream,
        ShardId=shard_id,
        **shard_iterator_opts)

    if debug: print(f'{bcolors.GREY20}shard iterator\n{pp.pformat(r)}{bcolors.ENDC}', file=sys.stderr);

    itr = r['ShardIterator']

    more_data = True
    i = 0
    n = 0
    format = opts.get('format')
    while more_data:
        if debug: print(f'\n\n{bcolors.GREY20}fetch {i} itr:{itr}{bcolors.ENDC}', file=sys.stderr)
        while True:
            try:
                r = client.get_records(ShardIterator=itr)
                if debug: print(pp.pformat(r), file=sys.stderr)
                break
            except client.exceptions.ProvisionedThroughputExceededException:
                print("caught ProvisionedThroughputExceededException", file=sys.stderr)
                time.sleep(delay_sleep)
                pass
            except Exception as e:
                print(e, file=sys.stderr)
                raise e

        for d in r['Records']:
            n += 1
            if stream in handler:
                d = handler[stream](d)
            print(f'\n{bcolors.GREY10}record {n}:{bcolors.ENDC}', file=sys.stderr)
            if format == 'python':
                pp.pprint(json.loads(d['Data']))
            elif format == 'json':
                sys.stdout.buffer.write(d['Data'])
                sys.stdout.buffer.write(b'\n')
                sys.stdout.buffer.flush()
            else:
                raise Exception(f'unknown format ${format}')
        itr = r['NextShardIterator']
        if args.limit and n >= args.limit:
            more_data = False
        elif itr == None:
            more_data = False
        elif r['MillisBehindLatest'] == 0:
            if args.follow:
                time.sleep(5)
            else:
                more_data = False
        else:
            # Sleep to avoid exceeding 5-calls-per-second limit.  This
            # rate-limit is applied across all consumers, and clients will
            # receive ProvisionedThroughputExceededException if it is
            # exceeded.
            time.sleep(delay_sleep)
        i += 1

########################################################################

parser = argparse.ArgumentParser(description='Dump a Kinesis stream.')
parser.add_argument('stream')
parser.add_argument(
    '-f', '--format', choices=['json', 'python'], default='python',
    help=f'output format (default python)')
parser.add_argument(
    '-p', '--profile', default=default_profile,
    help=f'specify AWS profile (default {default_profile})')
parser.add_argument(
    '--follow', action='store_true',
    help='continue waiting for more data when the end of the stream is reached')
parser.add_argument(
    '-n', '--limit', type=int,
    help='stop fetching more records when limit is reached')
time_group = parser.add_mutually_exclusive_group()
time_group.add_argument(
    '--start', type=datetime.datetime.fromisoformat,
    help='time to start fetching data from in ISO format (YYYY-MM-DD[THH[:MM[:SS]]])')
time_group.add_argument(
    '--since', type=parse_since,
    help='number of seconds in the past to start fetching data from, with optional suffix m:minutes, h:hours, d:days')
parser.add_argument(
    '--debug', action='store_true')
args = parser.parse_args()

debug = args.debug

start=None
if args.start:
    start = args.start
elif args.since:
    start = datetime.datetime.fromtimestamp(time.time() - args.since)

dump_stream(args.stream, profile=args.profile, follow=args.follow, limit=args.limit, start=start, format=args.format)
