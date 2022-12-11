#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
 #the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mailbox
import email.errors
import email.utils
import email.header
import time
import re
import os
import sys
import hashlib
import datetime
import plugins.utils.urlmisc

title = "Scanner for GNU Mailman Pipermail"
version = "0.1.0"

def accepts(source):
    """ Whether or not we think this is pipermail """
    if source['type'] == "pipermail":
        return True
    if source['type'] == 'mail':
        url = source['sourceURL']
        pipermail = re.match(r"(https?://.+/(archives|pipermail)/.+?)/?$", url)
        if pipermail:
            return True
    return False


def scan(KibbleBit, source):
    url = source['sourceURL']
    pipermail = re.match(r"(https?://.+/(archives|pipermail)/.+?)/?$", url)
    if pipermail:
        KibbleBit.pprint("Scanning Pipermail source %s" % url)
        skipped = 0
        jsa = []
        jsp = []
        source['steps']['mail'] = {
            'time': time.time(),
            'status': 'Downloading Pipermail statistics',
            'running': True,
            'good': True
        }
        KibbleBit.updateSource(source)
        
        dt = time.gmtime(time.time())
        firstYear = 1970
        year = dt[0]
        month = dt[1]
        if month <= 0:
            month += 12
            year -= 1
        months = 0
        
        knowns = {}
        
        # While we have older archives, continue to parse
        monthNames = ['December', 'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
        while firstYear <= year:
            gzurl = "%s/%04u-%s.txt.gz" % (url, year, monthNames[month])
            pd = datetime.date(year, month, 1).timetuple()
            dhash = hashlib.sha224((("%s %s") % (source['organisation'], gzurl)).encode('ascii', errors='replace')).hexdigest()
            found = False
            found = KibbleBit.exists('mailstats', dhash)
            if months <= 1 or not found: # Always parse this month's stats and the previous month :)
                months += 1
                mailFile = plugins.utils.urlmisc.unzip(gzurl)
                if mailFile:
                    try:
                        skipped = 0
                        messages = mailbox.mbox(mailFile)
                        
                        rawtopics = {}
                        posters = {}
                        no_posters = 0
                        emails = 0
                        senders = {}
                        for message in messages:
                            emails += 1
                            sender = message['from']
                            name = sender
                            if not 'subject' in message or not message['subject'] or not 'from' in message or not message['from']:
                                continue
                            
                            irt = message.get('in-reply-to', None)
                            if not irt and message.get('references'):
                                irt = message.get('references').split("\n")[0].strip()
                            replyto = None
                            if irt and irt in senders:
                                replyto = senders[irt]
                                print("This is a reply to %s" % replyto)
                            raw_subject = re.sub(r"^[a-zA-Z]+\s*:\s*", "", message['subject'], count=10)
                            raw_subject = re.sub(r"[\r\n\t]+", "", raw_subject, count=10)
                            if not raw_subject in rawtopics:
                                rawtopics[raw_subject] = 0
                            rawtopics[raw_subject] += 1
                            m = re.match(r"(.+?) at (.+?) \((.*)\)$", message['from'], flags=re.UNICODE)
                            if m:
                                name = m.group(3).strip()
                                sender = m.group(1) + "@" + m.group(2)
                            else:
                                m = re.match(r"(.+)\s*<(.+)>", message['from'], flags=re.UNICODE)
                                if m:
                                    name = m.group(1).replace('"', "").strip()
                                    sender = m.group(2)
                            if not sender in posters:
                                posters[sender] = {
                                    'name': name,
                                    'email': sender
                                }
                            senders[message.get('message-id', "??")] = sender
                            mdate = email.utils.parsedate_tz(message['date'])
                            mdatestring = time.strftime("%Y/%m/%d %H:%M:%S", time.gmtime(email.utils.mktime_tz(mdate)))
                            if not sender in knowns:
                                sid = hashlib.sha1( ("%s%s" % (source['organisation'], sender)).encode('ascii', errors='replace')).hexdigest()
                                knowns[sender] = KibbleBit.exists('person', sid)
                            if not sender in knowns:
                                KibbleBit.append('person',
                                    {
                                    'name': name,
                                    'email': sender,
                                    'organisation': source['organisation'],
                                    'id' :hashlib.sha1( ("%s%s" % (source['organisation'], sender)).encode('ascii', errors='replace')).hexdigest()
                                })
                                knowns[sender] = True
                            jse = {
                                'organisation': source['organisation'],
                                'sourceURL': source['sourceURL'],
                                'sourceID': source['sourceID'],
                                'date': mdatestring,
                                'sender': sender,
                                'replyto': replyto,
                                'subject': message['subject'],
                                'address': sender,
                                'ts': email.utils.mktime_tz(mdate),
                                'id': message['message-id']
                            }
                            KibbleBit.append('email', jse)
                            
                        for sender in posters:
                            no_posters += 1
                        i = 0
                        topics = 0
                        for key in rawtopics:
                            topics += 1
                        for key in reversed(sorted(rawtopics, key= lambda x: x)):
                            val = rawtopics[key]
                            i += 1
                            if i > 10:
                                break
                            KibbleBit.pprint("Found top 10: %s (%s emails)" % (key, val))
                            shash = hashlib.sha224(key.encode('ascii', errors='replace')).hexdigest()
                            md = time.strftime("%Y/%m/%d %H:%M:%S", pd)
                            mlhash = hashlib.sha224(( ("%s%s%s%s") % (key, source['sourceURL'], source['organisation'], md)).encode('ascii', errors='replace')).hexdigest() # one unique id per month per mail thread
                            jst = {
                                'organisation': source['organisation'],
                                'sourceURL': source['sourceURL'],
                                'sourceID': source['sourceID'],
                                'date': md,
                                'emails': val,
                                'shash': shash,
                                'subject': key,
                                'ts': time.mktime(pd),
                                'id': mlhash
                            }
                            KibbleBit.index('mailtop', mlhash, jst)
                        
                        jso = {
                            'organisation': source['organisation'],
                            'sourceURL': source['sourceURL'],
                            'sourceID': source['sourceID'],
                            'date': time.strftime("%Y/%m/%d %H:%M:%S", pd),
                            'authors': no_posters,
                            'emails': emails,
                            'topics': topics
                        }
                        KibbleBit.index('mailstats', dhash, jso)               
                        
                        os.unlink(mailFile)
                    except Exception as err:
                        KibbleBit.pprint("Couldn't parse %s, skipping: %s" % (gzurl, err))
                        skipped += 1
                        if skipped > 12:
                            KibbleBit.pprint("12 skips in a row, breaking off (no more data?)")
                            break
                else:
                    KibbleBit.pprint("Couldn't find %s, skipping." % gzurl)
                    skipped += 1
                    if skipped > 12:
                        KibbleBit.pprint("12 skips in a row, breaking off (no more data?)")
                        break
            month -= 1            
            if month <= 0:
                month += 12
                year -= 1
        
        source['steps']['mail'] = {
            'time': time.time(),
            'status': 'Mail archives successfully scanned at ' + time.strftime("%Y/%m/%d %H:%M:%S", time.gmtime(time.time())),
            'running': False,
            'good': True
        }
        KibbleBit.updateSource(source)
    else:
        KibbleBit.pprint("Invalid Pipermail URL detected: %s" % url, True)
        source['steps']['mail'] = {
            'time': time.time(),
            'status': 'Invalid or malformed URL detected!',
            'running': False,
            'good': False
        }
        KibbleBit.updateSource(source)
    