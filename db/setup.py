#!/usr/bin/env python3
from database import *
import json
from multiprocessing import cpu_count
from threading import Thread
from tqdm import tqdm

# bunch of constants because string typos in keynames would be the death of the database
NAME = 'name'
SPEC = 'specialty'

ADDR = 'address'
STREET = 'street'
CITY = 'city'
STATE = 'state'
ZIP = 'zip'

FILE = '../scraping/scraped_data.jsonl'
s = Session(AUTH)

def ignore(obj):
    global hrefs
    """Filter function to purge data which is not usefull for testing.

    Doctors without reviews or facilities are considered useless."""

    if not obj['reviews'] or not obj['data']['facilities']: # remove entries lacking reviews or a hospital
        return False

    if (obj['href'] in hrefs): #checking for dups
        return False
    hrefs.append(obj['href'])

    if 'United States' not in obj['data']['facilities'][0]['address']:
            #or 'FL' not in obj['data']['facilities'][0]['address']:
        return False
    for i in range(len(obj['reviews'])):
        rev = obj['reviews'][i]
        if rev['helpful_votes'] == None:
            rev['helpful_votes'] = '0'
    return True

def deserialize()->list:
    """Deserializes & filters the scraped data"""
    global hrefs
    hrefs = []

    data = []
    with open(FILE, 'r') as file:
        for line in file:
            data.append(json.loads(line))
    data = list(filter(ignore, data))
    return data

def _import(entries):
    """Formats the data and sends it to the database"""

    for e in tqdm(entries):
        h = dict(e['data']['facilities'][0]) #hospital("facilities")
        addr = h['address'].split(', ')
        if len(addr) == 5:
            street, city, state, _, zip = h['address'].split(', ')
        elif len(addr) == 6:
            street, apt, city, state, _, zip = h['address'].split(', ')
            street = ', '.join([street, apt])
        else:
            continue

        hos = {NAME:h[NAME],
                STREET:street,
                CITY: city,
                STATE: state,
                ZIP: zip}
        
        doc = {NAME:e[NAME],
               SPEC:e[SPEC],
               REV:e['reviews']}

        s._importDoctor(doc, hos)

def cleanup():
    #input('Waiting for input...')
    s.deleteUser('unknown')
    s._executeQuery('MATCH (n) DETACH DELETE n')

def importScrapedData(max=None):
    s.createUser({'username':'unknown','password':'password'})

    data = deserialize()
    data.sort(key=lambda x: len(x['reviews']))

    CC = cpu_count()
    threads = []
    for i in range(CC):
        t = Thread(target=_import, args=(data[i:max:CC],))
        threads.append(t)
        t.start()
    [t.join for t in threads]

def makeIndexes():
    def makeIndex(iName,labels, properties):
        s._executeQuery(f"""DROP INDEX {iName} IF EXISTS""")
        s._executeQuery(f"""
                        CREATE FULLTEXT INDEX {iName} IF NOT EXISTS
                        FOR (n:{'|'.join(labels)})
                        ON EACH[{','.join(['n.'+p for p in properties])}]
                        """)

    makeIndex('names',[DOC,HOS],[NAME,'specialty'])

if __name__ == '__main__':
    if input('Clean & Import Data? (y/n)').lower() == 'y':
        max = input('Limit (press enter for no limit): ')
        max = int(max) if max != '' else None
        print('Deleting existing data..."')
        cleanup()
        print('Importing scraped data...')
        importScrapedData(max)
        print('\n'*cpu_count())
        print('Import sucessful.')

    print('Creating indexes...')
    makeIndexes()
    print('\nDone')
