#!/usr/bin/env python

import datetime
import sys

from psycopg2 import IntegrityError, InternalError

from django.core.management import setup_environ
from codereview import settings

setup_environ(settings)

from django.contrib.auth.models import User

def main():

    if len(sys.argv) != 2:
        print """Missing path to import file
Expected a csv as: 
    'username', 'email', 'encryptedpwd'"""
        sys.exit(0)
        
    now = datetime.datetime.now()
   
    for l in open(sys.argv[1]):
        un, em, cr = l.split(',')

        try:
            User.objects.get(username=un)
            print "Ommiting duplicate user %s" % (un,)
            continue
        except User.DoesNotExist:
            pass   
        
        u = User(username=un,email=em,password=cr)
            
        try:     
            u.save()
            print "Saved %s" % (un,)
        except InternalError:
            print "psycopg choked on %s for some reason" % (un,)

if __name__ == "__main__":
    main()
