"""Tests for upload.py, the CLI tool which allows uploading a diff patch or set of patches, for review"""

import unittest
import upload

class testUploadDiff(unittest.TestCase):
    def setUp(self):
        pass
    
    """Test that if a file is submitted for its first review that it is uploaded in its entirety"""
    def testSingleFileNew(self):
        upload.main

        
    def tearDown(self):
        pass