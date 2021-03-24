#! /usr/bin/env python3

# A little class to make the syntax for dealing with metadata a little nicer.
class Metadata(dict):
    md = {}

    def __init__(self, *args, **kwargs):
        self.update(*args, **kwargs)

    def __getattr__(self, key):
        return self[key] if key in self else None

    # `md('key1', 'key2', ...)` returns a dict containing only the listed
    # keys.  This allows us to do `**md(...)` to copy those keys and values
    # into another dict.
    def __call__(self, *keys):
        rv = {}
        for key_from in keys:
            if isinstance(key_from, tuple):
                (key_from, key_to) = key_from
            else:
                key_to = key_from
            if key_from in self:
                rv[key_to] = self[key_from]

        return rv

########################################################################

host = 'public.fbot-sandbox.me'
user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:86.0) Gecko/20100101 Firefox/86.0'
merchant_id = 'c4612c73-4ab5-4336-bb77-74f60aa37fc7'

md = Metadata(
    merchantId = merchant_id,
    campaignId = 'b5e5928f-1fc8-4cb3-adb7-11c0c4031be7',
    widgetId = 'd7ec7070-c0ed-46b5-8610-e5f9a8a78b46',
    widgetConfigId = 'd7ec7070-c0ed-46b5-8610-e5f9a8a78b46',
    widgetDisplayName = 'Advocate Sitewide Overlay',
    variantId = '6ca4df9b-b907-4810-baf8-387a83c0c24b',
    screenLabel = 'Thanks State',
    screenId = 'b09bd1c2-caf9-4288-b3eb-a050fdf066bb',
    customerEmail = 'john.doe@example.com',
    customerName = 'John Doe',
    subscribe = 'no',
)

import base64
import json
import re
import requests
import sys
import urllib.parse

# Run this block to enable logging of HTTP requests and responses.
if False:
    import logging

    # These two lines enable debugging at httplib level (requests->urllib3->http.client)
    # You will see the REQUEST, including HEADERS and DATA, and RESPONSE with HEADERS but without DATA.
    # The only thing missing will be the response.body which is not logged.
    try:
        import http.client as http_client
    except ImportError:
        # Python 2
        import httplib as http_client
    http_client.HTTPConnection.debuglevel = 1

    # You must initialize logging, otherwise you'll not see debug output.
    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    requests_log = logging.getLogger("requests.packages.urllib3")
    requests_log.setLevel(logging.DEBUG)
    requests_log.propagate = True


import pprint
pp = pprint.PrettyPrinter(indent=4, compact=True)

# Some parameters are converted to JSON, then base64-encoded.
def encode_base64_json(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode('ascii'))

# Some parameters are converted to JSON, then URL-encoded, then base64-encoded.
def encode_base64_url_json(d):
    return base64.urlsafe_b64encode(urllib.parse.quote(json.dumps(d)).encode('ascii'))


# Fetch the profile.
def get_profile():
    b = {
        "c": 8,                     # screen.colorDepth
        "h": 480,                   # window.screen.height
        "w": 640,                   # window.screen.width
        "je": 'false',              # java enabled
        "l": "en-US",               # navigator.language
        "p": "MacIntel",            # navigator.platform
        "hc": 6,                    # navigator.hardwareConcurrency
    }

    profile_url = f'https://{host}/events/{merchant_id}/profile'

    r = requests.get(profile_url, params={'b': encode_base64_url_json(b)})

    pp.pprint(r)
    print(r.text)

    # Parse the profile out of the body.
    match = re.search(r'__setProfile__\(\"([^\"]+)\"', r.text)
    if not match:
        print(f'unable to parse profile in {r.text}', file=sys.stderr)
        sys.exit(1)
    profile = match.group(1)

    # Parse the globalId cookie out of the set-cookie header.
    # set-cookie: globalId=b8a9c0f5-04e2-4f0b-b3aa-7a0a8fa2ecc6; ...
    if 'set-cookie' in r.headers:
        match = re.search(r'globalId=([\w\-]+)', r.headers['set-cookie'])
        if not match:
            print(f'unable to parse profile_id in {r.headers["set-cookie"]}', file=sys.stderr)
            sys.exit(1)
        global_id = match.group(1)

    return { 'profile': profile, 'global_id': global_id }

# GETs a track event.
def pub_track_get(type, payload, md, profile):
    headers = {
        'Cookie': f'globalId={profile["global_id"]}',
    }
    metadata = md('widgetDisplayName')
    r = requests.get(f'https://{host}/track/', headers=headers, params={
        **md('merchantId'),
        'metadata': encode_base64_json(metadata),
        'payload': encode_base64_url_json(payload),
        'type': type,
        'tracker': profile['profile'],
    })
    pp.pprint([ r, r.text ]);
    return r.text

# POSTs a track event.
def pub_track_post(type, payload, profile):
    headers = {
        'Authorization': profile['profile'],
        'Cookie': f'globalId={profile["global_id"]}',
    }
    data = {
        'type': type,
        'payload': payload,
        **md('merchantId', 'campaignId'),
    }
    # Copy some metadata fields from the payload to the base if they exist.
    # (kp == payload key, km == metadata key)
    for kp in ('customerEmail', ('widgetId', 'widgetConfigId'), 'variantId'):
        if isinstance(kp, tuple):
            (kp, km) = kp
        else:
            km = kp

        if kp in payload:
            data[km] = payload[kp]

    r = requests.post(f'https://{host}/events/{merchant_id}/track', headers=headers, data=json.dumps(data))
    pp.pprint([ r, r.text ])
    return r.text

def widget_view(md, profile):
    payload = md('campaignId', 'merchantId', ('widgetDisplayName', 'name'), 'variantId', 'widgetConfigId')
    return pub_track_get('widget_view', payload, md, profile)

def get_purl(md, profile):
    headers = {
        'Cookie': f'globalId={profile["global_id"]}',
    }
    r = requests.get(f'https://{host}/share/referral/short', headers=headers, params={
        **md('merchantId', 'campaignId', 'widgetConfigId', 'widgetId', 'variantId',
             ('customerEmail', 'email'), ('customerName', 'name'), 'subscribe'),
        'channel': 'purl',
    })
    pp.pprint([ r, r.text ]);
    return r.text

def copy_purl(referral_code, md, profile):
    payload = {
        'name': 'widget_event',
        'action': 'copy_purl',
        'value': referral_code,
        **md('merchantId', 'campaignId', 'widgetConfigId', 'widgetId', 'variantId',
             'customerEmail', 'customerName', 'subscribe',
             'screenLabel', 'screenId')
    }
    return pub_track_post('widget_event', payload, profile)


print('\n\nget_profile');
p = get_profile()
pp.pprint(p)

print('\n\nwidget_view');
r = widget_view(md, p)
pp.pprint(r)

print('\n\nget_purl');
r = get_purl(md, p)
pp.pprint(r)
rr = json.loads(r)
referral_code = rr['data']['code']
referral_link = rr['data']['link']

print('\n\ncopy_purl');
r = copy_purl(referral_code, md, p)
pp.pprint(r)

print('\n\nfollow referral link');
ua_header = {
    'User-Agent': user_agent,
}
r = requests.get(referral_link,headers=ua_header)
pp.pprint([r, r.text])

sys.exit(0)
