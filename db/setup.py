#!/usr/bin/env python3
from database import *
import json

NAME = 'name'
SPEC = 'specialty'
ADDR = 'address'

FILE = '../scraping/scraped_data.jsonl'

def ignore(obj):
    """Filter function to purge data which is not usefull for testing.

    Doctors without reviews or facilities are considered useless."""

    if not obj['reviews'] or not obj['data']['facilities']:
        return False
    return True

def deserialize():
    """Deserializes & filters the scraped data"""

    data = []
    with open(FILE, 'r') as file:
        for line in file:
            data.append(json.loads(line))
    data = list(filter(ignore, data))
    return data

def importScrapedData():
    s = Session(AUTH)
    for i,e in enumerate(deserialize()):
        print(f'{i+1} mississippi...')
        h = dict(e['data']['facilities'][0])
        s._importDoctor(
                {NAME:e[NAME],SPEC:e[SPEC]},
                {NAME:h[NAME],ADDR:h[ADDR]})

if __name__ == '__main__':
    importScrapedData()
