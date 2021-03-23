#! /usr/bin/env python3

host = 'public.fbot-sandbox.me'
merchant_id = 'c4612c73-4ab5-4336-bb77-74f60aa37fc7'
campaign_id = 'b5e5928f-1fc8-4cb3-adb7-11c0c4031be7'
widget_id = 'd7ec7070-c0ed-46b5-8610-e5f9a8a78b46'
variant_id = '6ca4df9b-b907-4810-baf8-387a83c0c24b'
user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:86.0) Gecko/20100101 Firefox/86.0'

screen_dict = {
    'screenLabel': 'Thanks State',
    'screenId': 'b09bd1c2-caf9-4288-b3eb-a050fdf066bb',
}

customer_dict = {
    'customerEmail': 'john.doe@example.com',
    'customerName': 'John Doe',
    'subscribe': 'no',
}

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
def pub_track_get(type, metadata, payload, profile):
    headers = {
        'Cookie': f'globalId={profile["global_id"]}',
    }
    r = requests.get(f'https://{host}/track/', headers=headers, params={
        'merchantId': merchant_id,
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
        'merchantId': merchant_id,
        'campaignId': campaign_id,
    }
    # Copy some metadata fields from the payload to the base if they exist.
    if 'widgetId' in payload:
        data['widgetConfigId'] = payload['widgetId']
    for p in ('customerEmail', 'variantId'):
        if p in payload:
            data[p] = payload[p]

    r = requests.post(f'https://{host}/events/{merchant_id}/track', headers=headers, data=json.dumps(data))
    pp.pprint([ r, r.text ])
    return r.text

def widget_view(profile):
    # curl 'https://public.fbot-sandbox.me/track/?merchantId=c4612c73-4ab5-4336-bb77-74f60aa37fc7&metadata=eyJ0aXRsZSI6IlRlc3QgU3RvcmUiLCJ1cmwiOiJodHRwczovL2h1bGxhYmFsb28udXMvZmJzdG9yZS8iLCJvcmlnaW4iOiJodHRwczovL2h1bGxhYmFsb28udXMiLCJwYXRobmFtZSI6Ii9mYnN0b3JlLyIsIndpZGdldERpc3BsYXlOYW1lIjoiQWR2b2NhdGUgU2l0ZXdpZGUgT3ZlcmxheSJ9&payload=JTdCJTIybWVyY2hhbnRJZCUyMiUzQSUyMmM0NjEyYzczLTRhYjUtNDMzNi1iYjc3LTc0ZjYwYWEzN2ZjNyUyMiUyQyUyMmNhbXBhaWduSWQlMjIlM0ElMjJiNWU1OTI4Zi0xZmM4LTRjYjMtYWRiNy0xMWMwYzQwMzFiZTclMjIlMkMlMjJ3aWRnZXRDb25maWdJZCUyMiUzQSUyMmQ3ZWM3MDcwLWMwZWQtNDZiNS04NjEwLWU1ZjlhOGE3OGI0NiUyMiUyQyUyMm5hbWUlMjIlM0ElMjJBZHZvY2F0ZSUyMFNpdGV3aWRlJTIwT3ZlcmxheSUyMiUyQyUyMnZhcmlhbnRJZCUyMiUzQSUyMjZjYTRkZjliLWI5MDctNDgxMC1iYWY4LTM4N2E4M2MwYzI0YiUyMiU3RA%3D%3D&type=widget_view&tracker=eyJhbGciOiJSUzI1NiJ9.YzQ2MTJjNzMtNGFiNS00MzM2LWJiNzctNzRmNjBhYTM3ZmM3Ojg3OTc4OGFiLWVmMjMtNGVkOC05ZWQ0LTBiMmEwNDg3NDk3ODozYWUzYTUzOC0yNTBlLTRmZTItYTg1Mi0xODk0MzlkZDNhMWM6MzgzNThmZTgtYTFmMy00NzFlLWJiMWUtMWI5Nzg1OTU5Yzk5Omh1bGxhYmFsb28udXM6MTYxNjQ1NTMyMzo6Og.v6VzSluUB5nw7yHcKjNfo6ndVhBBzVSDcNzGCv7hrZSKIRg8YJr-i-Gzfj6CoWbwiL-dhB36U5sjWb_l9amffGT15UZU31V7iZO-xjS6Sjx1I6Oglid5E1Cgtygb-vWbYuvOWEBTD_3v7O4FzQqLna2akElt4gcmnjWLVHTvdN4' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:86.0) Gecko/20100101 Firefox/86.0' -H 'Accept: image/webp,*/*' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'Connection: keep-alive' -H 'Referer: https://hullabaloo.us/fbstore/' -H 'Cookie: globalId=3ae3a538-250e-4fe2-a852-189439dd3a1c'
    payload = {
        'campaignId': campaign_id,
        'merchantId': merchant_id,
        'name': 'Advocate Sitewide Overlay',
        'variantId': variant_id,
        'widgetConfigId' : widget_id,
    }
    return pub_track_get('widget_view', {}, payload, profile)

def get_purl(profile):
    # https://public.fbot-sandbox.me/share/referral/short?merchantId=c4612c73-4ab5-4336-bb77-74f60aa37fc7&campaignId=b5e5928f-1fc8-4cb3-adb7-11c0c4031be7&widgetConfigId=d7ec7070-c0ed-46b5-8610-e5f9a8a78b46&email=home%40davidhull.org&channel=purl&seed=&prefix=&name=David%20Hull&subscribe=no&widgetId=d7ec7070-c0ed-46b5-8610-e5f9a8a78b46&utm=%7B%7D&variantId=6ca4df9b-b907-4810-baf8-387a83c0c24b
    headers = {
        'Cookie': f'globalId={profile["global_id"]}',
    }
    r = requests.get(f'https://{host}/share/referral/short', headers=headers, params={
        'merchantId': merchant_id,
        'campaignId': campaign_id,
        'channel': 'purl',
        'email': customer_dict['customerEmail'],
        'name': customer_dict['customerName'],
        'subscribe': customer_dict['subscribe'],
        'widgetConfigId': widget_id,
        'widgetId': widget_id,
        'variantId': variant_id,
    })
    pp.pprint([ r, r.text ]);
    return r.text

def copy_purl(referral_code, profile):
    # curl 'https://public.fbot-sandbox.me/events/c4612c73-4ab5-4336-bb77-74f60aa37fc7/track' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:86.0) Gecko/20100101 Firefox/86.0' -H 'Accept: application/json' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'Referer: https://hullabaloo.us/fbstore/' -H 'Authorization: eyJhbGciOiJSUzI1NiJ9.YzQ2MTJjNzMtNGFiNS00MzM2LWJiNzctNzRmNjBhYTM3ZmM3Ojg3OTc4OGFiLWVmMjMtNGVkOC05ZWQ0LTBiMmEwNDg3NDk3ODozYWUzYTUzOC0yNTBlLTRmZTItYTg1Mi0xODk0MzlkZDNhMWM6MzgzNThmZTgtYTFmMy00NzFlLWJiMWUtMWI5Nzg1OTU5Yzk5Omh1bGxhYmFsb28udXM6MTYxNjQ1NTMyMzo6Og.v6VzSluUB5nw7yHcKjNfo6ndVhBBzVSDcNzGCv7hrZSKIRg8YJr-i-Gzfj6CoWbwiL-dhB36U5sjWb_l9amffGT15UZU31V7iZO-xjS6Sjx1I6Oglid5E1Cgtygb-vWbYuvOWEBTD_3v7O4FzQqLna2akElt4gcmnjWLVHTvdN4' -H 'Content-Type: application/json' -H 'Origin: https://hullabaloo.us' -H 'Connection: keep-alive' -H 'TE: Trailers' --data-raw '{"type":"widget_event","payload":{"screenName":"b09bd1c2-caf9-4288-b3eb-a050fdf066bb","customerEmail":"home@davidhull.org","customerName":"David Hull","subscribe":"no","campaignId":"b5e5928f-1fc8-4cb3-adb7-11c0c4031be7","merchantId":"c4612c73-4ab5-4336-bb77-74f60aa37fc7","screenId":"b09bd1c2-caf9-4288-b3eb-a050fdf066bb","widgetConfigId":"d7ec7070-c0ed-46b5-8610-e5f9a8a78b46","name":"widget_event","action":"copy_purl","value":"5ktvupnn","screenLabel":"Thanks State","widgetId":"d7ec7070-c0ed-46b5-8610-e5f9a8a78b46"},"customerEmail":"home@davidhull.org","customerName":"David Hull","subscribe":"no","campaignId":"b5e5928f-1fc8-4cb3-adb7-11c0c4031be7","merchantId":"c4612c73-4ab5-4336-bb77-74f60aa37fc7","screenId":"b09bd1c2-caf9-4288-b3eb-a050fdf066bb","widgetConfigId":"d7ec7070-c0ed-46b5-8610-e5f9a8a78b46","sessionId":"2021-03-23T17:41:50.420Z|3787208808849237","variantId":"6ca4df9b-b907-4810-baf8-387a83c0c24b"}'
    payload = {
        'name': 'widget_event',
        'action': 'copy_purl',
        'merchantId': merchant_id,
        'campaignId': campaign_id,
        'value': referral_code,
        'widgetConfigId': widget_id,
        'widgetId': widget_id,
        'variantId': variant_id,
        **customer_dict,
        **screen_dict,
    }
    return pub_track_post('widget_event', payload, profile)

def post_email_share():
    pass
    # curl 'https://public.fbot-sandbox.me/share/email' -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:86.0) Gecko/20100101 Firefox/86.0' -H 'Accept: application/json' -H 'Accept-Language: en-US,en;q=0.5' --compressed -H 'Referer: https://hullabaloo.us/fbstore/' -H 'Authorization: eyJhbGciOiJSUzI1NiJ9.YzQ2MTJjNzMtNGFiNS00MzM2LWJiNzctNzRmNjBhYTM3ZmM3Ojg3OTc4OGFiLWVmMjMtNGVkOC05ZWQ0LTBiMmEwNDg3NDk3ODozYWUzYTUzOC0yNTBlLTRmZTItYTg1Mi0xODk0MzlkZDNhMWM6MzgzNThmZTgtYTFmMy00NzFlLWJiMWUtMWI5Nzg1OTU5Yzk5Omh1bGxhYmFsb28udXM6MTYxNjQ1NTMyMzo6Og.v6VzSluUB5nw7yHcKjNfo6ndVhBBzVSDcNzGCv7hrZSKIRg8YJr-i-Gzfj6CoWbwiL-dhB36U5sjWb_l9amffGT15UZU31V7iZO-xjS6Sjx1I6Oglid5E1Cgtygb-vWbYuvOWEBTD_3v7O4FzQqLna2akElt4gcmnjWLVHTvdN4' -H 'Content-Type: application/json' -H 'Origin: https://hullabaloo.us' -H 'Connection: keep-alive' -H 'TE: Trailers' --data-raw $'{"name":"David Hull","sendReminder":"no","message":"Hey, check out Hull Test\041 I love their products and I think you will too. I\u2019m giving you 20% off your first order. You can thank me later :)","recipients":["david.hull+20210323a@friendbuy.com"],"email":"home@davidhull.org","widgetConfigId":"d7ec7070-c0ed-46b5-8610-e5f9a8a78b46","merchantId":"c4612c73-4ab5-4336-bb77-74f60aa37fc7","campaignId":"b5e5928f-1fc8-4cb3-adb7-11c0c4031be7","widgetId":"d7ec7070-c0ed-46b5-8610-e5f9a8a78b46","channel":"email","sessionId":"2021-03-23T17:41:50.420Z|3787208808849237","utm":"{}","variantId":"6ca4df9b-b907-4810-baf8-387a83c0c24b"}'

    # response:
    # {"data":{"status":"new","id":"df6ecca4-cfca-4573-bde4-29188bbb5940","convertedRecipients":[],"resentRecipients":[],"delayedRecipients":[],"cancelledRecipients":[],"logs":[],"attributes":{"name":"David Hull","sendReminder":"no","widgetConfigId":"d7ec7070-c0ed-46b5-8610-e5f9a8a78b46","merchantId":"c4612c73-4ab5-4336-bb77-74f60aa37fc7","channel":"email","sessionId":"2021-03-23T17:41:50.420Z|3787208808849237","utm":"{}"},"clickCountByRecipient":{},"campaignId":"b5e5928f-1fc8-4cb3-adb7-11c0c4031be7","merchantId":"c4612c73-4ab5-4336-bb77-74f60aa37fc7","channel":"email","referral":{"userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:86.0) Gecko/20100101 Firefox/86.0","advocate":{"name":"David Hull"},"ipAddress":"66.214.31.90","updatedOn":"2021-03-22T22:53:47.964Z","status":"active","email":"home@davidhull.org","channel":"email","code":"8wzg3rtr","campaignId":"b5e5928f-1fc8-4cb3-adb7-11c0c4031be7","widgetId":"d7ec7070-c0ed-46b5-8610-e5f9a8a78b46","profileId":"879788ab-ef23-4ed8-9ed4-0b2a04874978","crawlerVisit":"2021-03-11T23:44:58.157Z","globalId":"3ae3a538-250e-4fe2-a852-189439dd3a1c","merchantIdBase":"c4612c73-4ab5-4336-bb77-74f60aa37fc7:8wzg3rtr","prefix":null,"robotVisit":"2020-12-12T02:46:52.768Z","campaignIdChannelEmail":"b5e5928f-1fc8-4cb3-adb7-11c0c4031be7:email:home@davidhull.org:6ca4df9b-b907-4810-baf8-387a83c0c24b","base":"8wzg3rtr","iterator":0,"seed":null,"createdOn":"2020-11-30T16:31:50.531Z","firstClick":"2020-12-14T17:40:28.037Z","variantId":"6ca4df9b-b907-4810-baf8-387a83c0c24b","expireOn":null,"merchantId":"c4612c73-4ab5-4336-bb77-74f60aa37fc7"},"source":"widget","recipients":["david.hull+20210323a@friendbuy.com"],"recipientCount":1,"variantId":"6ca4df9b-b907-4810-baf8-387a83c0c24b","email":"home@davidhull.org","originalEmail":"home@davidhull.org","profileId":"879788ab-ef23-4ed8-9ed4-0b2a04874978","globalId":"3ae3a538-250e-4fe2-a852-189439dd3a1c","message":"Hey, check out Hull Test! I love their products and I think you will too. I’m giving you 20% off your first order. You can thank me later :)","ipAddress":"66.214.31.90","ua":{"ua":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:86.0) Gecko/20100101 Firefox/86.0","browser":{"name":"Firefox","version":"86.0","major":"86"},"engine":{"name":"Gecko","version":"86.0"},"os":{"name":"Mac OS","version":"10.15"},"device":{},"cpu":{}},"widgetId":"d7ec7070-c0ed-46b5-8610-e5f9a8a78b46","merchantIdReferralCode":"c4612c73-4ab5-4336-bb77-74f60aa37fc7:8wzg3rtr","createdOn":"2021-03-23T17:55:23.875Z","expireOn":1711216524}}

print('\n\nget_profile');
p = get_profile()
pp.pprint(p)

print('\n\nwidget_view');
r = widget_view(p)
pp.pprint(r)

print('\n\nget_purl');
r = get_purl(p)
pp.pprint(r)
rr = json.loads(r)
referral_code = rr['data']['code']
referral_link = rr['data']['link']

print('\n\ncopy_purl');
r = copy_purl(referral_code, p)
pp.pprint(r)

print('\n\nfollow referral link');
ua_header = {
    'User-Agent': user_agent,
}
r = requests.get(referral_link,headers=ua_header)
pp.pprint([r, r.text])

sys.exit(0)
