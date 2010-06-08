""" Interface to difflib.py providing unified diffs only:

"""

import sys, os, time, difflib, optparse

def unified_diff(fromfile, tofile):
    # we're passing these as arguments to the diff function
    fromdate = time.ctime(os.stat(fromfile).st_mtime)
    todate = time.ctime(os.stat(tofile).st_mtime)
    fromlines = open(fromfile, 'U').readlines()
    tolines = open(tofile, 'U').readlines()

   
    diff = difflib.unified_diff(fromlines, tolines, fromfile, tofile,
                                    fromdate, todate, n=3)
   
    return diff


