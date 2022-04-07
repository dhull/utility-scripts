#! /usr/bin/env python3

default_profile = 'fbot-sandbox'
debug = False

import datetime
import time

import argparse
import base64
import json
import os
import pathlib
import pprint
import re

pp = pprint.PrettyPrinter(indent=4, compact=True)

# Use awscli's virtualenv if we're not already running in one.
if 'VIRTUAL_ENV' not in os.environ:
    print('using awscli virtualenv')
    activate_script = pathlib.Path('/usr/local/bin/aws').resolve().parent.joinpath('activate_this.py')
    exec(open(activate_script).read(), dict(__file__=activate_script))

print(os.environ['VIRTUAL_ENV'])

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
    if debug: print(f'{bcolors.GREY20}shards\n{pp.pformat(shards)}{bcolors.ENDC}')
    shard_id = shards['Shards'][0]['ShardId']

    if opts.get('start', 0):
        # print(f'using start {opts["start"]}')
        shard_iterator_opts = { 'ShardIteratorType': 'AT_TIMESTAMP', 'Timestamp': opts['start'] }
    else:
        # print('using trim_horizon')
        shard_iterator_opts = { 'ShardIteratorType': 'TRIM_HORIZON' }

    r = client.get_shard_iterator(
        StreamName=stream,
        ShardId=shard_id,
        **shard_iterator_opts)

    if debug: print(f'{bcolors.GREY20}shard iterator\n{pp.pformat(r)}{bcolors.ENDC}');

    itr = r['ShardIterator']

    more_data = True
    i = 0
    n = 0
    while more_data:
        if debug: print(f'\n\n{bcolors.GREY20}fetch {i} itr:{itr}{bcolors.ENDC}')
        r = client.get_records(ShardIterator=itr)
        pp.pprint(r)
        for d in r['Records']:
            n += 1
            if stream in handler:
                d = handler[stream](d)
            print(f'\n{bcolors.GREY10}record {n}:{bcolors.ENDC}')
            pp.pprint(json.loads(d['Data']))
        itr = r['NextShardIterator']
        if args.limit and n >= args.limit:
            more_data = False
        elif len(r['Records']) == 0:
            if args.follow:
                time.sleep(5)
            else:
                more_data = False
        else:
            # Sleep to avoid exceeding 5-calls-per-second limit.  This
            # rate-limit is applied across all consumers, and clients will
            # receive ProvisionedThroughputExceededException if it is
            # exceeded.
            time.sleep(0.5)
        i += 1

########################################################################

parser = argparse.ArgumentParser(description='Dump a Kinesis stream.')
parser.add_argument('stream')
parser.add_argument(
    '-p', '--profile', default=default_profile,
    help=f'specify AWS profile (default {default_profile})')
parser.add_argument(
    '-f', '--follow', action='store_true',
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

dump_stream(args.stream, profile=args.profile, follow=args.follow, limit=args.limit, start=start)
