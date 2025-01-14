#!/usr/bin/env python

import sys
import logging
import base64
import re
from datetime import datetime, timedelta, date
import os
from simple_salesforce import Salesforce
import json

logger = logging.getLogger("salesforce_timecard")


class TimecardEntry(object):

    def __init__(self, cfg='~/.pse_timecard.json'):

        self.cfg_file = os.path.expanduser(cfg)
        with open(self.cfg_file) as f:
            self.cfg = json.load(f)

        self.sf = Salesforce(username=self.cfg['username'],
                             password=base64.b64decode(
                                 self.cfg['password']).decode(),
                             security_token=self.cfg['token'],
                             sandbox=self.cfg.get("sandbox", None),
                             client_id='FF'
                             )

        self.contact_id = self.get_contact_id(self.cfg['username'])
        self.assignments = self.get_assignments(self.contact_id)
        self.ASSIGNMENTS_MAPPING = []

        today = date.today()
        day = today.strftime("%d-%m-%Y")
        # day = '02-07-2019'
        self.get_week(day)

    def get_week(self, day):
        dt = datetime.strptime(day, '%d-%m-%Y')
        self.start = dt - timedelta(days=dt.weekday())
        self.end = self.start + timedelta(days=6)

    def _dynamic_project_assignment(self, description):
        """Retrieves PXxxx or IP xxx xxx from the description and tries to find assignment_id"""
        phrase = description
        m = re.findall("^(PX\d+|IP [\w-]+(?: \w+){0,3}) ?-", description)
        if m:
            phrase = m[0]
            if phrase in self.ASSIGNMENTS_MAPPING:
                return self.ASSIGNMENTS_MAPPING[phrase]
        # find in assignments
        for k, v in self.assignments.items():
            if v['project_name'].startswith(phrase):
                self.ASSIGNMENTS_MAPPING[phrase] = {'pse__Project__c': v['project_id'],
                                                    'pse__Assignment__c': v['assignment_id']}
                return self.ASSIGNMENTS_MAPPING[phrase]


    def list_timecard(self,details, start, end):
        
        fields = ["Id", "Name", "OwnerId", "PROJECT_ID__c", "pse__Approved__c", "pse__Project__c", 
        "pse__Start_Date__c", "pse__End_Date__c", 
        "pse__Monday_Hours__c", "pse__Monday_Notes__c", 
        "pse__Tuesday_Hours__c", "pse__Tuesday_Notes__c" ,
        "pse__Wednesday_Hours__c", "pse__Wednesday_Notes__c", 
        "pse__Thursday_Hours__c", "pse__Thursday_Notes__c",
        "pse__Friday_Hours__c", "pse__Friday_Notes__c", 
        "pse__Status__c", "pse__Submitted__c"]
        if details:
            fields = fields + ["CreatedById", "CreatedDate",  "IsDeleted", "LastModifiedById", "LastModifiedDate", 
            "LastReferencedDate", "LastViewedDate", 
            "pse__Assignment__c", "pse__Audit_Notes__c", "pse__Billable__c",  "pse__Resource__c", 
            "pse__Location_Mon__c", "pse__Location_Tue__c", "pse__Location_Wed__c",  
            "pse__Location_Thu__c", "pse__Location_Fri__c",
             "pse__Saturday_Hours__c", "pse__Saturday_Notes__c", "pse__Location_Sat__c", 
             "pse__Sunday_Hours__c", "pse__Sunday_Notes__c", "pse__Location_Sun__c", 
             "pse__Timecard_Notes__c"]

        SQL = '''select 
                {}
                from pse__Timecard_Header__c 
                where 
                pse__Start_Date__c = {} and pse__End_Date__c = {} and
                pse__Resource__c = '{}'
                '''.format(
                    ", ".join(fields),
                    start,
                    end,
                    self.contact_id,
                )
        logger.debug(SQL)
        results = self.sf.query_all(SQL)
        rs = []
        if len(results['records']) > 0:

            for r in results['records']:
                r.pop('attributes', None)
                # adding Project name
                if r.get("pse__Assignment__c", "") in self.assignments.keys():
                    r["pse__Project_Name__c"] = self.assignments[r["pse__Assignment__c"]]["project_name"]
                rs.append(r)          
            return rs
        else:
            logger.warn("No time card")
            return []

    def get_contact_id(self, email):
        name_part = email.split('@')[0]
        r = self.sf.query(
            "select Id, Name, Email from Contact where pse__Is_Resource__c = true and Email LIKE '{}@cloudreach.%'".format(
                name_part))
        # r = self.sf.Contact.get_by_custom_id('Email', email)
        return r['records'][0]['Id']

    def get_assignments(self, contact_id):

        SQL = '''select Id, Name, pse__Project__c, pse__Project__r.Name, pse__Project__r.pse__Is_Billable__c from pse__Assignment__c 
        where pse__Resource__c = '{}' and 
        Open_up_Assignment_for_Time_entry__c = false and 
        pse__Closed_for_Time_Entry__c = false and
        pse__Exclude_from_Billing__c = false 
        '''.format(
            contact_id)

        logger.debug(SQL)
        results = self.sf.query_all(SQL)
        assignments = {}
        for r in results['records']:
            assignments[r['Id']] = {'assignment_id': r['Id'], 'project_id': r['pse__Project__c'],
                                    'project_name': r['pse__Project__r']['Name'],
                                    'billable': r['pse__Project__r']['pse__Is_Billable__c']}

        return assignments

    def add_time_entry(self, assignment_id, day_n, hours, notes):
        
        self.assignment_id = assignment_id
        new_timecard = {
            "pse__Start_Date__c": self.start.strftime('%Y-%m-%d'),
            "pse__End_Date__c": self.end.strftime('%Y-%m-%d'),
            'pse__Resource__c': self.contact_id,
            # 'pse__Monday_Hours__c': 8.0,
            # 'pse__Monday_Notes__c': 'Stuff on monday',
            # 'pse__Tuesday_Hours__c': 8.0,
            # 'pse__Tuesday_Notes__c': 'Stuff on tuesday',
            # 'pse__Wednesday_Hours__c': 8.0,
            # 'pse__Wednesday_Notes__c': 'Stuff on wednesday',
            # 'pse__Thursday_Hours__c': 8.0,
            # 'pse__Thursday_Notes__c': 'Stuff on thursday',
            # 'pse__Friday_Hours__c': 4.0,
            # 'pse__Friday_Notes__c': 'Stuff on friday',
        }

        if self.assignment_id in self.assignments.keys():
            new_timecard['pse__Assignment__c'] = self.assignment_id
            new_timecard['pse__Project__c'] = self.assignments[self.assignment_id]['project_id']
            SQL = '''select Id from pse__Timecard_Header__c 
                where 
                pse__Start_Date__c = {} and pse__End_Date__c = {} and
                pse__Resource__c = '{}' and 
                pse__Assignment__c = '{}'  and 
                pse__Project__c = '{}' 
                '''.format(
                self.start.strftime('%Y-%m-%d'),
                self.end.strftime('%Y-%m-%d'),
                self.contact_id,
                self.assignment_id,
                self.assignments[self.assignment_id]['project_id'],
            )
        else:
            #most probably is a project without assigment
            new_timecard['pse__Project__c'] = self.assignment_id
            SQL = '''select Id from pse__Timecard_Header__c 
                where 
                pse__Start_Date__c = {} and pse__End_Date__c = {} and
                pse__Resource__c = '{}' and 
                pse__Project__c = '{}' 
                '''.format(
                self.start.strftime('%Y-%m-%d'),
                self.end.strftime('%Y-%m-%d'),
                self.contact_id,
                self.assignment_id,
            )
        
        new_timecard["pse__" + day_n + "_Hours__c"] = hours
        new_timecard["pse__" + day_n + "_Notes__c"] = notes

        logger.debug(SQL)
        results = self.sf.query_all(SQL)
        logger.debug(json.dumps(new_timecard, indent=4))
        if len(results['records']) > 0:
            logger.debug("required update")
            try:
                self.sf.pse__Timecard_Header__c.update(
                    results['records'][0]["Id"], new_timecard)
            except:
                logger.error("failed on update")
                logger.error(sys.exc_info()[1])
                sys.exit(1)

        else:
            try:
                self.sf.pse__Timecard_Header__c.create(new_timecard)
            except:
                logger.error("failed on creation")
                logger.error(sys.exc_info()[1])
                sys.exit(1)
