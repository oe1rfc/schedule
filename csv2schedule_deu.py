# -*- coding: UTF-8 -*-

import sys, os, locale, argparse
import requests
import json
from collections import OrderedDict
import dateutil.parser
from datetime import datetime
from datetime import timedelta
import csv
import hashlib
import pytz


if sys.version_info[0] < 3:
    reload(sys)
    sys.setdefaultencoding('utf-8')

days = []
de_tz = pytz.timezone('Europe/Amsterdam')
#local = False
locale.setlocale(locale.LC_ALL, 'de_DE.UTF-8')

# some functions used in multiple files of this collection
import voc.tools

parser = argparse.ArgumentParser()
parser.add_argument('acronym', help='the event acronym')
parser.add_argument('--offline', action='store_true')
parser.add_argument('--url', action='store')

parser.add_argument('-f', '--my-foo', default='foobar')


print('')

args = parser.parse_args()
acronym = args.acronym
if args.url:
    source_csv_url = args.url
    offline = args.offline
else:
    offline = True
    print("No URL given, using CSV file from disk\n")

# specifies the date format used in the CSV file respectivly the google docs spreadsheet
date_format = '%Y-%m-%d %H:%M' 
default_talk_length = timedelta(minutes=30)

#end config



template = { "schedule":  OrderedDict([
        ("version", "1.0"),
        ("conference",  OrderedDict([
            ("title", ""), 
            ("acronym", acronym),
            ("daysCount", 1),
            ("start", ""),
            ("end",   ""),
            ("timeslot_duration", "00:15"),
            ("days", [])
        ]))
    ])
}

output_dir = "./{}/".format(acronym)
#output_dir = '/srv/www/schedule/' + acronym
if not os.path.exists(output_dir):
    os.mkdir(output_dir) 
os.chdir(output_dir)


def main():
    process(acronym, 0, source_csv_url)

def process(ort, base_id, source_csv_url):
    global template, days
    
    out = template
    
    
    print('Processing ' + ort)
    
    if not offline:
        print(" requesting schedule source from url")
        schedule_r = requests.get(
            source_csv_url, 
            verify=False #'cacert.pem'
        )
        
        # don't ask me why google docs announces by header? it will send latin1 and then sends utf8...
        schedule_r.encoding = 'utf-8'
        
        if schedule_r.ok is False:
            raise Exception("  Requesting schedule from CSV source url failed, HTTP code {0} from {1}.".format(schedule_r.status_code, source_csv_url))
        
        with open('schedule-' + ort + '.csv', 'w') as f:
            f.write(schedule_r.text)

    print(" parsing CSV file")
    csv_schedule = []
    max_date = None
    min_date = None
    with open('schedule-' + ort + '.csv', 'r') as f:
        reader = csv.reader(f) #, encoding='utf-8'
        
        # first header
        keys = next(reader)
        # store conference title from top left cell into schedule
        out['schedule']['conference']['title'] = keys[0].split('#')[0].strip()
        out['schedule']['version'] = keys[0].split('#')[1].replace('Version', '').strip()
        last = keys[0] = 'meta'
        keys_uniq = []
        for i, k in enumerate(keys):
            if k != '': 
                last = k.strip()
                keys_uniq.append(last)
            keys[i] = last
        
        # second header
        keys2 = next(reader)

        # data rows
        for row in reader:
            i = 0
            items = OrderedDict([ (k, OrderedDict()) for k in keys_uniq ])
            row_iter = iter(row)
            
            for value in row_iter:
                value = value.strip()
                if keys2[i] != '' and value != '':
                    items[keys[i]][keys2[i]] = value.decode('utf-8')
                i += 1
            
            if len(items['meta']) > 0 and 'Titel' in items['meta']:
                csv_schedule.append(items)
                start_time = datetime.strptime( items['meta']['Datum'] + ' ' + items['meta']['Uhrzeit'], date_format)
                if min_date is None or start_time < min_date:
                    min_date = start_time
                if max_date is None or start_time > max_date:
                    max_date = start_time
    
    #print json.dumps(csv_schedule, indent=4) 
    
    
    out['schedule']['conference']['start'] = min_date.strftime('%Y-%m-%d')
    out['schedule']['conference']['end'] = max_date.strftime('%Y-%m-%d')
    out['schedule']['conference']['daysCont'] = (max_date - min_date).days + 1
    
    print(" converting to schedule ")
    conference_start_date = dateutil.parser.parse(out['schedule']['conference']['start'])

    for i in range(out['schedule']['conference']['daysCount']):
        date = conference_start_date + timedelta(days=i)
        start = date + timedelta(hours=10) # conference day starts at 10:00
        end = start + timedelta(hours=17)  # conference day lasts 17 hours
        
        days.append( OrderedDict([
            ('index', i),
            ('date' , date),
            ('start', start),
            ('end', end),
        ]))
             
        out['schedule']['conference']['days'].append(OrderedDict([
            ('index', i),
            ('date' , date.strftime('%Y-%m-%d')),
            ('start', start.isoformat()),
            ('end', end.isoformat()),
            ('rooms', OrderedDict())
        ]))
    
    for event in csv_schedule:
        start_time = datetime.strptime( event['meta']['Datum'] + ' ' + event['meta']['Uhrzeit'], date_format)
        # TODO check if start_time of next (or other) event overlaps with end_time calculated from default_talk_length
        end_time   = start_time + default_talk_length 
        duration   = (end_time - start_time).seconds/60
        
        id = str(base_id + int(event['meta']['ID']))
        room = event['meta']['Raum']
        guid = voc.tools.gen_uuid(hashlib.md5(ort + room + id).hexdigest())
        
        event_n = OrderedDict([
            ('id', id),
            ('guid', guid),
            # ('logo', None),
            ('date', start_time.isoformat()),
            ('start', start_time.strftime('%H:%M')),
            ('duration', '%d:%02d' % divmod(duration, 60) ),
            ('room', room),
            ('slug', '-'.join([acronym, id, voc.tools.normalise_string(event['meta']['Titel'])])),
            ('title', event['meta']['Titel']),
            ('subtitle', event['meta'].get('Untertitel', '')),
            ('track', ''),
            ('type', ''),
            ('language', event['meta'].get('Sprache', 'de') ),
            ('abstract', ''),
            ('description', event['meta'].get('Beschreibung', '') ),
            ('do_not_record', event['meta'].get('Aufzeichnung?', '') == 'nein'),
            ('persons', [ OrderedDict([
                ('id', 0),
                ('full_public_name', p.strip()),
                #('#text', p),
            ]) for p in event['Vortragende'].values() ]),
            ('links', [])
        ])
        
        #print event_n['title']
        
        day = (start_time - conference_start_date).days + 1
        day_rooms = out['schedule']['conference']['days'][day-1]['rooms']
        if room not in day_rooms:
            day_rooms[room] = list()
        day_rooms[room].append(event_n)
        
        
    
    #print json.dumps(schedule, indent=2)
    
    print(" writing results to disk")
    with open('schedule-' + ort + '.json', 'w') as fp:
        json.dump(out, fp, indent=4)
        
    with open('schedule-' + ort + '.xml', 'w') as fp:
        fp.write(voc.tools.dict_to_schedule_xml(out));
    
    # TODO: Validate XML via schema file
    print(' end')
    


if __name__ == '__main__':
    main()