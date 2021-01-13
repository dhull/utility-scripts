#! /usr/bin/env python3

default_profile = 'fbot-sandbox'
debug = False

import datetime
import time

import argparse
import json
import os
import pathlib
import pprint
import sys

pp = pprint.PrettyPrinter(indent=4, compact=True)

# Use awscli's virtualenv if we're not already running in one.
# This works until awscli-2.1.18, when the activate_this.py module was removed/moved.
if 'VIRTUAL_ENV' not in os.environ:
    print('using awscli virtualenv', file=sys.stderr)
    # aws and activate_this.py's paths are something like:
    #   /usr/local/Cellar/awscli/2.1.18/libexec/bin/aws
    #   /usr/local/Cellar/awscli/2.1.18/libexec/bin/activate_this.py
    # This was broken in awscli 2.1.18 when activate_this was moved to:
    #   /usr/local/Cellar/awscli/2.1.18/libexec/lib/python3.9/site-packages/virtualenv/activation/python/activate_this.py
    activate_script = pathlib.Path('/usr/local/bin/aws').resolve().parent.joinpath('activate_this.py')
    exec(open(activate_script).read(), dict(__file__=activate_script))

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
    # ansicolor has 24 levels of grayscale beginning at 232.
    GREY0       = f'\033[38;5;{232 +  0}m' # black
    GREY10      = f'\033[38;5;{232 + 10}m'
    GREY20      = f'\033[38;5;{232 + 20}m'
    GREY23      = f'\033[38;5;{232 + 23}m' # white


# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/core/session.html
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html

import botocore.session
import botocore.exceptions

# https://stackoverflow.com/questions/36558646/how-to-convert-from-dynamodb-wire-protocol-to-native-python-object-manually-with
try:
    from boto3.dynamodb.types import TypeDeserializer
except ImportError as e:
    # Location in awscli v2
    from awscli.customizations.dynamodb.types import TypeDeserializer


def dump_table(table, profile, **opts):
    limit = opts.get('limit')
    delay = opts.get('delay', 30) # seconds

    session = botocore.session.Session(profile=profile)
    client = session.create_client('dynamodb')

    deser = TypeDeserializer()

    more_data = True
    i = 0
    n = 0
    start_key = None
    while more_data:
        if debug: print(f'{bcolors.GREY20}fetch {i} n:{n} with delay:{delay}{bcolors.ENDC}', file=sys.stderr)

        scan_opts = {}
        if limit: scan_opts['Limit'] = limit - n
        if start_key: scan_opts['ExclusiveStartKey'] = start_key

        try:
            r = client.scan(TableName=table, **scan_opts)

            # pp.pprint(r)
            # print("=====")

            for d in r['Items']:
                n += 1
                # print(f'\n{bcolors.GREY10}record {n}:{bcolors.ENDC}')
                # pp.pprint(json.loads(d['Data']))
                # pp.pprint(d)
                # pp.pprint(deser.deserialize({'M': d}))
                print(json.dumps(deser.deserialize({'M': d}), default=defaultencode))

            start_key = r.get('LastEvaluatedKey', {})

        except client.exceptions.ProvisionedThroughputExceededException as e:
            print(f'{bcolors.WARNING}caught {e}{bcolors.ENDC}', file=sys.stderr)
            delay = delay * 2

        if not start_key:
            more_data = False
        elif limit and n >= limit:
            more_data = False
        else:
            # Sleep to avoid exceeding 5-calls-per-second limit.  This
            # rate-limit is applied across all consumers, and clients will
            # receive ProvisionedThroughputExceededException if it is
            # exceeded.
            time.sleep(delay)
        i += 1

########################################################################

# https://stackoverflow.com/questions/1960516/python-json-serialize-a-decimal-object
# Allow JSON encoding of Decimal objects (which are returned by
# TypeDeserializer).

from decimal import Decimal

class fakefloat(float):
    def __init__(self, value):
        self._value = value
    def __repr__(self):
        return str(self._value)

def defaultencode(o):
    if isinstance(o, Decimal):
        # Subclass float with custom repr?
        return fakefloat(o)
    raise TypeError(repr(o) + " is not JSON serializable")

# json.dumps([10.20, "10.20", Decimal('10.20')], default=defaultencode)

########################################################################

parser = argparse.ArgumentParser(description='Dump a DynamoDB table.')
parser.add_argument('table')
parser.add_argument(
    '-p', '--profile', default=default_profile,
    help=f'specify AWS profile (default {default_profile})')
parser.add_argument(
    '-n', '--limit', type=int,
    help='stop fetching more records when limit is reached')
parser.add_argument(
    '-d', '--delay', type=int,
    help='delay between calls to avoid exceeding provisioned throughput')
parser.add_argument(
    '--debug', action='store_true')
args = parser.parse_args()

debug = args.debug

dump_table(args.table, profile=args.profile, limit=args.limit)
